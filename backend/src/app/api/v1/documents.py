"""Documents API router v1."""
import uuid
import time
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, BackgroundTasks, HTTPException, Form
from pydantic import BaseModel

from app.db.models import Document, Chunk
from app.db.engine import get_session
from app.ingestion.extractor import process_pdf
from app.ingestion import chunk_text
from app.schemas.api import DocumentUploadResponse, DocumentStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def process_document_background(document_id: str, file_path: str, chunking_strategy: str = "structured"):
    """Background task to process the uploaded document."""
    logger.info("[Background] Starting document processing for doc_id='%s' (strategy='%s')", document_id, chunking_strategy)
    total_start = time.time()
    
    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error("[Background] Document not found in DB: doc_id='%s'", document_id)
            return
        doc.status = "processing"
        db.commit()
        logger.info("[Background] Status set to 'processing' for doc_id='%s'", document_id)

    try:
        logger.info("[Background] Step 1/3: Extracting text from PDF...")
        step_start = time.time()
        clean_text = process_pdf(Path(file_path))
        logger.info("[Background] Step 1/3 complete in %.2fs (text length: %s chars)",
                    time.time() - step_start, f"{len(clean_text):,}")
        
        logger.info("[Background] Step 2/3: Chunking text (strategy='%s')...", chunking_strategy)
        step_start = time.time()
        chunks = chunk_text(clean_text, strategy=chunking_strategy)
        logger.info("[Background] Step 2/3 complete in %.2fs (%d chunks created)",
                    time.time() - step_start, len(chunks))
        
        logger.info("[Background] Step 3/4: Saving chunks to database...")
        step_start = time.time()
        saved_chunks_data = []
        with get_session() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                for i, c in enumerate(chunks, 1):
                    cat_val = c.category.value if hasattr(c.category, 'value') else str(c.category)
                    chunk_id = str(uuid.uuid4())
                    db_chunk = Chunk(
                        id=chunk_id,
                        document_id=doc.id,
                        text=c.text,
                        category=cat_val,
                        section_heading=c.section_heading,
                        chapter=c.chapter
                    )
                    db.add(db_chunk)
                    saved_chunks_data.append({
                        "id": chunk_id,
                        "document_id": doc.id,
                        "text": c.text,
                        "category": cat_val,
                        "section_heading": c.section_heading,
                        "chapter": c.chapter
                    })
                doc.status = "ready"
                db.commit()
                logger.info("[Background] Step 3/4 complete in %.2fs (%d chunks saved)",
                            time.time() - step_start, len(chunks))

        logger.info("[Background] Step 4/4: Indexing chunks into ChromaDB...")
        step_start = time.time()
        from app.pipeline.service import get_pipeline_service
        service = get_pipeline_service()
        service.index_document_chunks(saved_chunks_data)
        logger.info("[Background] Step 4/4 complete in %.2fs", time.time() - step_start)
        
        total_elapsed = time.time() - total_start
        logger.info("[Background] Document processing COMPLETE for doc_id='%s' in %.2fs (status=ready, chunks=%d)",
                    document_id, total_elapsed, len(chunks))
                    
    except Exception as e:
        total_elapsed = time.time() - total_start
        logger.error("[Background] Document processing FAILED for doc_id='%s' after %.2fs: %s",
                     document_id, total_elapsed, e, exc_info=True)
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
    chunking_strategy: str = Form("structured")
):
    """Upload PDF file."""
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
        logger.info("Document record saved to DB (doc_id='%s', status=pending, strategy='%s')", doc_id, chunking_strategy)
        
    background_tasks.add_task(process_document_background, doc_id, str(file_path), chunking_strategy)
    logger.info("Background processing task queued for doc_id='%s'", doc_id)
    
    return DocumentUploadResponse(id=doc_id, status="pending", message="Dokumen berhasil diunggah dan pemrosesan dimulai.")

@router.get("/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(document_id: str):
    """Get document status."""
    logger.debug("GET document status: doc_id='%s'", document_id)
    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("Document not found: doc_id='%s'", document_id)
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
        created_at_str = doc.uploaded_at.strftime("%Y-%m-%d %H:%M") if doc.uploaded_at else None
        logger.debug("Document status: doc_id='%s', status='%s'", document_id, doc.status)
        return DocumentStatusResponse(
            id=doc.id, 
            subject=doc.subject, 
            status=doc.status, 
            filename=doc.filename,
            chunking_strategy=doc.chunking_strategy or "structured",
            created_at=created_at_str,
            error_message=doc.error_message
        )

@router.get("/", response_model=List[DocumentStatusResponse])
def list_documents():
    """List all documents."""
    logger.debug("GET list all documents")
    with get_session() as db:
        docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
        logger.debug("Returning %d documents", len(docs))
        result = []
        for d in docs:
            created_at_str = d.uploaded_at.strftime("%Y-%m-%d %H:%M") if d.uploaded_at else None
            result.append(DocumentStatusResponse(
                id=d.id, 
                subject=d.subject, 
                status=d.status, 
                filename=d.filename,
                chunking_strategy=d.chunking_strategy or "structured",
                created_at=created_at_str,
                error_message=d.error_message
            ))
        return result

@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str):
    """Get all chunks for a specific document."""
    logger.debug("GET chunks for document_id='%s'", document_id)
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
    """Delete document and associated chunks."""
    logger.info("DELETE document: doc_id='%s'", document_id)
    with get_session() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("Delete failed - document not found: doc_id='%s'", document_id)
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
        db.delete(doc)
        db.commit()
        logger.info("Document deleted: doc_id='%s', filename='%s'", document_id, doc.filename)
        
    try:
        from app.pipeline.service import get_pipeline_service
        service = get_pipeline_service()
        service.dense_index.delete_by_document(document_id)
    except Exception as e:
        logger.warning("Failed to delete vectors from ChromaDB for doc_id='%s': %s", document_id, e)

    return {"status": "deleted"}
