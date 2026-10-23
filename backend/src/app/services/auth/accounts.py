"""Moving, purging and deleting owned data (documents cascade to sessions, questions and chunks)."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.models.db_models import ChatSession, Document, User
from app.services.documents import delete_documents, remove_document_files

logger = logging.getLogger(__name__)


def claim_guest_data(db: Session, guest_id: str | None, user_id: str) -> None:
    """Saat tamu masuk/daftar, semua dokumen & chat dari browser itu menjadi milik akunnya."""
    if not guest_id:
        return
    docs = (
        db.query(Document)
        .filter(Document.user_id.is_(None), Document.guest_id == guest_id)
        .update({Document.user_id: user_id, Document.guest_id: None})
    )
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id.is_(None), ChatSession.guest_id == guest_id)
        .update({ChatSession.user_id: user_id, ChatSession.guest_id: None})
    )
    if docs or sessions:
        logger.info("Claimed guest data for user_id='%s': %d document(s), %d session(s)", user_id, docs, sessions)


def claim_legacy_data(db: Session, user_id: str) -> None:
    """Data dari sebelum fitur login (tanpa pemilik) diwarisi akun pertama."""
    docs = (
        db.query(Document)
        .filter(Document.user_id.is_(None), Document.guest_id.is_(None))
        .update({Document.user_id: user_id})
    )
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id.is_(None), ChatSession.guest_id.is_(None))
        .update({ChatSession.user_id: user_id})
    )
    logger.info("First account user_id='%s' inherited %d document(s), %d session(s)", user_id, docs, sessions)


def is_first_user(db: Session) -> bool:
    return db.query(User.id).first() is None


def delete_user_account(db: Session, user: User) -> None:
    """Hapus akun beserta semua dokumen, chat, dan soalnya."""
    removed = delete_documents(db, db.query(Document).filter(Document.user_id == user.id).all())
    db.flush()
    # Sesi milik akun ini yang tidak ikut terhapus lewat dokumennya
    for s in db.query(ChatSession).filter(ChatSession.user_id == user.id).all():
        db.delete(s)
    db.delete(user)
    db.commit()
    remove_document_files(removed)
    logger.info("Deleted account user_id='%s' with %d document(s)", user.id, len(removed))


def purge_stale_guest_data(now: datetime | None = None) -> int:
    """Hapus semua data tamu yang browser-nya tidak aktif melewati batas TTL. Mengembalikan jumlah tamu."""
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=get_settings().auth.guest_ttl_hours)
    cutoff = cutoff.replace(tzinfo=None)  # SQLite menyimpan UTC tanpa zona waktu
    with get_session() as db:
        activity = (
            db.query(Document.guest_id.label("gid"), Document.last_active_at.label("at"))
            .filter(Document.user_id.is_(None), Document.guest_id.isnot(None))
            .union_all(
                db.query(ChatSession.guest_id, ChatSession.last_active_at)
                .filter(ChatSession.user_id.is_(None), ChatSession.guest_id.isnot(None))
            )
            .subquery()
        )
        last_seen = db.query(activity.c.gid, func.max(activity.c.at)).group_by(activity.c.gid).all()
        stale = {gid for gid, last in last_seen if last is None or last < cutoff}
        # Jangan menghapus di tengah generasi soal yang masih berjalan
        stale -= {
            gid
            for (gid,) in db.query(ChatSession.guest_id)
            .filter(ChatSession.guest_id.in_(stale), ChatSession.generation_status == "running")
            .all()
        }
        if not stale:
            return 0

        removed = delete_documents(
            db, db.query(Document).filter(Document.user_id.is_(None), Document.guest_id.in_(stale)).all()
        )
        db.flush()
        for s in db.query(ChatSession).filter(ChatSession.user_id.is_(None), ChatSession.guest_id.in_(stale)).all():
            db.delete(s)
        db.commit()
    remove_document_files(removed)
    logger.info("Purged data of %d inactive guest(s) (%d document(s))", len(stale), len(removed))
    return len(stale)
