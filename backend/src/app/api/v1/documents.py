"""Documents API router v1."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile

from app.api.deps import get_owner
from app.core.database import get_session
from app.models.db_models import Chunk, Document
from app.schemas.api_schemas import DocumentStatusResponse, DocumentUploadResponse
from app.services.auth.data import remove_document_files
from app.services.auth.guest_quota import GUEST_LIMIT_MESSAGES, can_use, consume
from app.services.auth.owner import Owner
from app.services.ingestion.pipeline import process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_RAW_DATA_DIR = Path("data/raw")
_NOT_FOUND = "Dokumen tidak ditemukan"


def _owned_document(db, document_id: str, owner: Owner) -> Document:
    doc = db.query(Document).filter(Document.id == document_id, owner.clause(Document)).first()
    if not doc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return doc


def _document_response(doc: Document) -> DocumentStatusResponse:
    return DocumentStatusResponse.model_validate({
        "id": doc.id,
        "subject": doc.subject,
        "status": doc.status,
        "filename": doc.filename,
        "chunking_strategy": doc.chunking_strategy or "fixed",
        "created_at": doc.uploaded_at.strftime("%Y-%m-%d %H:%M") if doc.uploaded_at is not None else None,
        "error_message": doc.error_message,
    })


@router.post("/", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    subject: str = Form(...),
    chunking_strategy: str = Form("fixed"),
    owner: Owner = Depends(get_owner),
):
    """Upload PDF file with selected chunking strategy."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        logger.warning("Upload rejected: non-PDF file '%s'", file.filename)
        raise HTTPException(status_code=400, detail="Hanya file dengan ekstensi .pdf yang didukung.")
    with get_session() as db:
        if not can_use(db, owner, "upload"):
            raise HTTPException(status_code=403, detail=GUEST_LIMIT_MESSAGES["upload"])

    doc_id = str(uuid.uuid4())
    _RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _RAW_DATA_DIR / f"{doc_id}_{file.filename}"
    content = await file.read()
    file_path.write_bytes(content)

    logger.info("Upload received: file='%s', subject='%s', strategy='%s', size=%.2fMB, doc_id='%s'",
                file.filename, subject, chunking_strategy, len(content) / (1024 * 1024), doc_id)

    with get_session() as db:
        db.add(Document(
            id=doc_id,
            subject=subject,
            status="pending",
            filename=file.filename,
            filepath=str(file_path),
            chunking_strategy=chunking_strategy,
            **owner.fields(),
        ))
        consume(db, owner, "upload")
        db.commit()

    background_tasks.add_task(process_document, doc_id, str(file_path), chunking_strategy)
    return DocumentUploadResponse(id=doc_id, status="pending", message="Dokumen berhasil diunggah dan pemrosesan dimulai.")


@router.get("/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(document_id: str, owner: Owner = Depends(get_owner)):
    """Get document status."""
    with get_session() as db:
        return _document_response(_owned_document(db, document_id, owner))


@router.get("/", response_model=list[DocumentStatusResponse])
def list_documents(owner: Owner = Depends(get_owner)):
    """List the requester's documents."""
    with get_session() as db:
        docs = db.query(Document).filter(owner.clause(Document)).order_by(Document.uploaded_at.desc()).all()
        return [_document_response(d) for d in docs]


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str, owner: Owner = Depends(get_owner)):
    """Get all chunks for a specific document."""
    with get_session() as db:
        _owned_document(db, document_id, owner)

        chunks = db.query(Chunk).filter(Chunk.document_id == document_id).order_by(Chunk.created_at).all()
        return [
            {
                "id": c.id,
                "document_id": c.document_id,
                "text": c.text,
                "category": c.category,
                "section_heading": c.section_heading,
                "chapter": c.chapter,
                "word_count": len(c.text.split()) if c.text is not None else 0,
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at is not None else None,
            }
            for c in chunks
        ]


@router.delete("/{document_id}")
def delete_document(document_id: str, owner: Owner = Depends(get_owner)):
    """Delete document, its chunks and raw file from SQLite, ChromaDB and disk."""
    logger.info("DELETE document: doc_id='%s'", document_id)
    with get_session() as db:
        doc = _owned_document(db, document_id, owner)
        filepath = str(doc.filepath) if doc.filepath is not None else None
        db.delete(doc)
        db.commit()

    remove_document_files([(document_id, filepath)])
    return {"status": "deleted"}
