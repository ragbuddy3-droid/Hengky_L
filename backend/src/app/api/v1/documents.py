"""Documents API router v1."""

import logging

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import DbDep, OwnerDep
from app.models.db_models import Chunk, Document
from app.schemas.api_schemas import DocumentStatusResponse, DocumentUploadResponse
from app.services.auth.guest_quota import GUEST_LIMIT_MESSAGES, can_use
from app.services.auth.owner import Owner
from app.services.documents import create_document, delete_documents, owned_document, remove_document_files
from app.services.ingestion.pipeline import process_document
from app.services.ingestion.validation import DocumentRejected, check_upload_size, validate_pdf_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_NOT_FOUND = "Dokumen tidak ditemukan"


def _owned_document(db: Session, document_id: str, owner: Owner) -> Document:
    doc = owned_document(db, document_id, owner)
    if not doc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return doc


def _document_response(doc: Document) -> DocumentStatusResponse:
    return DocumentStatusResponse.model_validate({
        "id": doc.id,
        "subject": doc.subject,
        "status": doc.status,
        "filename": doc.filename,
        "created_at": doc.uploaded_at.strftime("%Y-%m-%d %H:%M") if doc.uploaded_at is not None else None,
        "error_message": doc.error_message,
        "warning_message": doc.warning_message,
    })


@router.post("/", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    owner: OwnerDep,
    db: DbDep,
    subject: str = Form(...),
):
    """Upload a PDF and start ingestion in the background."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        logger.warning("Upload rejected: non-PDF file '%s'", file.filename)
        raise HTTPException(status_code=400, detail="Hanya file dengan ekstensi .pdf yang didukung.")
    if not can_use(db, owner, "upload"):
        raise HTTPException(status_code=403, detail=GUEST_LIMIT_MESSAGES["upload"])

    try:
        check_upload_size(file.size)
        content = await file.read()
        validate_pdf_bytes(content)
    except DocumentRejected as e:
        logger.warning("Upload rejected: file='%s': %s", file.filename, e.user_message)
        raise HTTPException(status_code=400, detail=e.user_message) from e

    doc = create_document(db, owner, file.filename, subject, content)
    db.commit()

    background_tasks.add_task(process_document, doc.id, str(doc.filepath))
    return DocumentUploadResponse(id=doc.id, status="pending", message="Dokumen berhasil diunggah dan pemrosesan dimulai.")


@router.get("/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(document_id: str, owner: OwnerDep, db: DbDep):
    """Get document status."""
    return _document_response(_owned_document(db, document_id, owner))


@router.get("/", response_model=list[DocumentStatusResponse])
def list_documents(owner: OwnerDep, db: DbDep):
    """List the requester's documents."""
    docs = db.query(Document).filter(owner.clause(Document)).order_by(Document.uploaded_at.desc()).all()
    return [_document_response(d) for d in docs]


@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str, owner: OwnerDep, db: DbDep):
    """Get all chunks for a specific document."""
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
def delete_document(document_id: str, owner: OwnerDep, db: DbDep):
    """Delete document, its chunks and raw file from SQLite, ChromaDB and disk."""
    logger.info("DELETE document: doc_id='%s'", document_id)
    removed = delete_documents(db, [_owned_document(db, document_id, owner)])
    db.commit()
    remove_document_files(removed)
    return {"status": "deleted"}
