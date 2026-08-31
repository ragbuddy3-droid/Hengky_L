"""Documents API router v1."""

import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile

from app.core.database import get_session
from app.graph.nodes import get_shared_dense_index
from app.models.db_models import Chunk, Document
from app.schemas.api_schemas import DocumentStatusResponse, DocumentUploadResponse
from app.services.ingestion.extractor import process_pdf, process_pdf_pages
from app.services.ingestion.factory import chunk_pages, chunk_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def process_document_background(document_id: str, file_path: str, chunking_strategy: str = "section_aware"):
    """Background task to extract, chunk, and index an uploaded PDF with page-level tracking."""
    logger.info("[Background] Starting document processing for doc_id='%s' (strategy='%s')", document_id, chunking_strategy)
    total_start = time.time()

    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error("[Background] Document not found in DB: doc_id='%s'", document_id)
            return
        doc.status = "processing"
        db.commit()

    try:
        # Step 1: Page-aware text extraction & cleaning
        logger.info("[Background] Step 1/4: Extracting pages from PDF...")
        step_start = time.time()
        pages = process_pdf_pages(Path(file_path))
        logger.info("[Background] Step 1/4 complete in %.2fs (%d pages extracted)", time.time() - step_start, len(pages))

        # Step 2: Section-aware Chunking
        logger.info("[Background] Step 2/4: Chunking text (strategy='%s')...", chunking_strategy)
        step_start = time.time()
        if pages:
            chunks = chunk_pages(pages, strategy=chunking_strategy)
        else:
            raw_text = process_pdf(Path(file_path))
            chunks = chunk_text(raw_text, strategy=chunking_strategy)
        logger.info("[Background] Step 2/4 complete in %.2fs (%d chunks created)", time.time() - step_start, len(chunks))

        # Step 3: Saving chunks to SQLite
        logger.info("[Background] Step 3/4: Saving chunks to database...")
        step_start = time.time()
        saved_chunks_data = []

        with get_session() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                for c in chunks:
                    chunk_id = str(uuid.uuid4())
                    db_chunk = Chunk(
                        id=chunk_id,
                        document_id=doc.id,
                        text=c.text,
                        category=c.category,
                        section_heading=c.section_heading,
                        chapter=c.chapter,
                        page_number=getattr(c, "page_number", 1) or 1,
                        chunk_index=getattr(c, "chunk_index", 0) or 0,
                        section_type=getattr(c, "section_type", "materi_pokok") or "materi_pokok",
                    )
                    db.add(db_chunk)
                    saved_chunks_data.append({
                        "id": chunk_id,
                        "document_id": doc.id,
                        "text": c.text,
                        "category": c.category,
                        "section_heading": c.section_heading,
                        "chapter": c.chapter,
                        "page_number": getattr(c, "page_number", 1) or 1,
                        "chunk_index": getattr(c, "chunk_index", 0) or 0,
                        "section_type": getattr(c, "section_type", "materi_pokok") or "materi_pokok",
                    })

                doc.status = "ready"
                db.commit()

        logger.info("[Background] Step 3/4 complete in %.2fs (%d chunks saved)", time.time() - step_start, len(saved_chunks_data))

        # Step 4: Indexing into ChromaDB
        logger.info("[Background] Step 4/4: Indexing chunks into ChromaDB...")
        step_start = time.time()
        dense_idx = get_shared_dense_index()
        dense_idx.index_chunks(saved_chunks_data)
        logger.info("[Background] Step 4/4 complete in %.2fs", time.time() - step_start)

        elapsed = time.time() - total_start
        logger.info("[Background] Document processing COMPLETE for doc_id='%s' in %.2fs (chunks=%d)",
                    document_id, elapsed, len(saved_chunks_data))

    except Exception as e:
        elapsed = time.time() - total_start
        logger.error("[Background] Document processing FAILED for doc_id='%s' after %.2fs: %s",
                     document_id, elapsed, e, exc_info=True)
        with get_session() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = "failed"
                doc.error_message = str(e)
                db.commit()


@router.post("/", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    subject: str = Form(...),
    chunking_strategy: str = Form("section_aware")
):
    """Upload PDF file with selected chunking strategy."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        logger.warning("Upload rejected: non-PDF file '%s'", file.filename)
        raise HTTPException(status_code=400, detail="Hanya file dengan ekstensi .pdf yang didukung.")

    doc_id = str(uuid.uuid4())
    data_dir = Path("data/raw")
    data_dir.mkdir(parents=True, exist_ok=True)

    file_path = data_dir / f"{doc_id}_{file.filename}"
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)

    with open(file_path, "wb") as f:
        f.write(content)

    logger.info("Upload received: file='%s', subject='%s', strategy='%s', size=%.2fMB, doc_id='%s'",
                file.filename, subject, chunking_strategy, file_size_mb, doc_id)

    with get_session() as db:
        new_doc = Document(
            id=doc_id,
            subject=subject,
            status="pending",
            filename=file.filename,
            filepath=str(file_path),
            chunking_strategy=chunking_strategy
        )
        db.add(new_doc)
        db.commit()

    background_tasks.add_task(process_document_background, doc_id, str(file_path), chunking_strategy)
    return DocumentUploadResponse(id=doc_id, status="pending", message="Dokumen berhasil diunggah dan pemrosesan dimulai.")


@router.get("/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(document_id: str):
    """Get document status."""
    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

        created_at_str = doc.uploaded_at.strftime("%Y-%m-%d %H:%M") if doc.uploaded_at else None
        return DocumentStatusResponse(
            id=doc.id,
            subject=doc.subject,
            status=doc.status,
            filename=doc.filename,
            chunking_strategy=doc.chunking_strategy or "fixed",
            created_at=created_at_str,
            error_message=doc.error_message
        )


@router.get("/", response_model=list[DocumentStatusResponse])
def list_documents():
    """List all documents."""
    with get_session() as db:
        docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
        result = []
        for d in docs:
            created_at_str = d.uploaded_at.strftime("%Y-%m-%d %H:%M") if d.uploaded_at else None
            result.append(DocumentStatusResponse(
                id=d.id,
                subject=d.subject,
                status=d.status,
                filename=d.filename,
                chunking_strategy=d.chunking_strategy or "fixed",
                created_at=created_at_str,
                error_message=d.error_message
            ))
        return result


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str):
    """Get all chunks for a specific document."""
    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

        chunks = db.query(Chunk).filter(Chunk.document_id == document_id).order_by(Chunk.created_at).all()
        result = []
        for c in chunks:
            created_str = c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None
            word_count = len(c.text.split()) if c.text else 0
            result.append({
                "id": c.id,
                "document_id": c.document_id,
                "text": c.text,
                "category": c.category,
                "section_heading": c.section_heading,
                "chapter": c.chapter,
                "word_count": word_count,
                "created_at": created_str
            })
        return result


@router.delete("/{document_id}")
def delete_document(document_id: str):
    """Delete document and associated chunks from SQLite and ChromaDB."""
    logger.info("DELETE document: doc_id='%s'", document_id)
    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
        db.delete(doc)
        db.commit()

    try:
        dense_idx = get_shared_dense_index()
        dense_idx.delete_by_document(document_id)
    except Exception as e:
        logger.warning("Failed to delete vectors from ChromaDB for doc_id='%s': %s", document_id, e)

    return {"status": "deleted"}
