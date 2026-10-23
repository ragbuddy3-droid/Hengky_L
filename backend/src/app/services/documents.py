"""Uploaded documents: storing the PDF, ownership lookup, and deletion across SQLite, ChromaDB and disk."""

import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db_models import Document
from app.services.auth.guest_quota import consume
from app.services.auth.owner import Owner
from app.services.retrieval.retriever import delete_document_vectors

logger = logging.getLogger(__name__)

RemovedFiles = list[tuple[str, str | None]]  # (document id, raw PDF path) to clean up after the DB commit


def owned_document(db: Session, document_id: str, owner: Owner) -> Document | None:
    return db.query(Document).filter(Document.id == document_id, owner.clause(Document)).first()


def create_document(db: Session, owner: Owner, filename: str, subject: str, content: bytes) -> Document:
    """Write the PDF to data/raw, add a 'pending' document and use the guest's upload quota (not committed)."""
    doc_id = str(uuid.uuid4())
    raw_dir = get_settings().paths.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / f"{doc_id}_{filename}"
    file_path.write_bytes(content)

    logger.info("Upload received: file='%s', subject='%s', size=%.2fMB, doc_id='%s'",
                filename, subject, len(content) / (1024 * 1024), doc_id)
    doc = Document(id=doc_id, subject=subject, status="pending", filename=filename, filepath=str(file_path), **owner.fields())
    db.add(doc)
    consume(db, owner, "upload")
    return doc


def delete_documents(db: Session, docs: list[Document]) -> RemovedFiles:
    """Delete documents from the DB (cascading to chunks and sessions); returns what remove_document_files cleans up."""
    removed = [(d.id, d.filepath) for d in docs]
    for d in docs:
        db.delete(d)
    return removed


def remove_document_files(removed: RemovedFiles) -> None:
    """Delete the vectors and raw PDFs of documents already deleted from the DB."""
    for doc_id, filepath in removed:
        delete_document_vectors(doc_id)
        if filepath:
            try:
                Path(filepath).unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to remove raw file '%s': %s", filepath, e)
