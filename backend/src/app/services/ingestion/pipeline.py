"""Document ingestion pipeline: PDF extraction -> fixed chunking -> SQLite -> ChromaDB."""

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.database import get_session
from app.models.db_models import Chunk, Document
from app.services.auth.guest_quota import refund
from app.services.ingestion.extractor import extract_pages_from_pdf
from app.services.ingestion.factory import chunk_pages
from app.services.ingestion.validation import DocumentRejected, check_document
from app.services.retrieval.retriever import get_shared_dense_index, invalidate_sparse_cache

logger = logging.getLogger(__name__)


GENERIC_FAILURE_MESSAGE = "Terjadi kesalahan saat memproses buku. Coba hapus lalu unggah ulang."


def _set_document_status(
    document_id: str, status: str, error_message: str | None = None, warning_message: str | None = None,
) -> bool:
    values: dict[Any, Any] = {Document.status: status}
    if error_message is not None:
        values[Document.error_message] = error_message
    if warning_message is not None:
        values[Document.warning_message] = warning_message
    with get_session() as db:
        updated = db.query(Document).filter(Document.id == document_id).update(values)
        if status == "failed":
            doc = db.get(Document, document_id)
            refund(db, doc.guest_id if doc and doc.user_id is None else None, "upload")  # type: ignore[arg-type]
        db.commit()
        return bool(updated)


def _document_subject(document_id: str) -> str:
    with get_session() as db:
        doc = db.get(Document, document_id)
        return str(doc.subject) if doc else ""


def process_document(document_id: str, file_path: str) -> None:
    """Extract, chunk, store and index an uploaded PDF. The document becomes 'ready' only once it is searchable."""
    logger.info("[Ingestion] Starting doc_id='%s'", document_id)
    total_start = time.time()

    if not _set_document_status(document_id, "processing"):
        logger.error("[Ingestion] Document not found in DB: doc_id='%s'", document_id)
        return

    try:
        step_start = time.time()
        pages = extract_pages_from_pdf(Path(file_path))
        chunks = chunk_pages(pages)
        logger.info("[Ingestion] Extracted %d pages into %d chunks in %.2fs", len(pages), len(chunks), time.time() - step_start)

        step_start = time.time()
        warning = check_document(chunks, _document_subject(document_id))
        logger.info("[Ingestion] Content check passed in %.2fs (warning=%s)", time.time() - step_start, warning)

        step_start = time.time()
        rows: list[dict[str, Any]] = [
            {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "text": c.text,
                "category": c.category,
                "section_heading": c.section_heading,
                "chapter": c.chapter,
                "page_number": c.page_number or 1,
                "chunk_index": c.chunk_index or 0,
                "section_type": c.section_type or "materi_pokok",
            }
            for c in chunks
        ]
        with get_session() as db:
            db.add_all([Chunk(**row) for row in rows])
            db.commit()
        logger.info("[Ingestion] Saved %d chunks to SQLite in %.2fs", len(rows), time.time() - step_start)

        step_start = time.time()
        get_shared_dense_index().index_chunks(rows)
        invalidate_sparse_cache(document_id)
        logger.info("[Ingestion] Indexed chunks into ChromaDB in %.2fs", time.time() - step_start)

        _set_document_status(document_id, "ready", warning_message=warning)
        logger.info("[Ingestion] COMPLETE doc_id='%s' in %.2fs (chunks=%d)", document_id, time.time() - total_start, len(rows))

    except DocumentRejected as e:
        logger.info("[Ingestion] REJECTED doc_id='%s': %s", document_id, e.user_message)
        _set_document_status(document_id, "failed", e.user_message)
    except Exception as e:
        logger.error("[Ingestion] FAILED doc_id='%s' after %.2fs: %s", document_id, time.time() - total_start, e, exc_info=True)
        _set_document_status(document_id, "failed", GENERIC_FAILURE_MESSAGE)


def delete_document_vectors(document_id: str) -> None:
    """Remove a deleted document from the dense index and the BM25 cache."""
    invalidate_sparse_cache(document_id)
    try:
        get_shared_dense_index().delete_by_document(document_id)
    except Exception as e:
        logger.warning("Failed to delete vectors from ChromaDB for doc_id='%s': %s", document_id, e)
