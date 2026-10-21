"""Mode tamu hanya boleh sekali: unggah buku, buat sesi chat, dan minta soal."""

from typing import Literal

from sqlalchemy.orm import Session

from app.models.db_models import GuestUsage, utcnow
from app.services.auth.owner import Owner

QuotaKind = Literal["upload", "session", "generate"]

_COLUMNS: dict[QuotaKind, str] = {
    "upload": "uploaded_at",
    "session": "session_created_at",
    "generate": "generated_at",
}

GUEST_LIMIT_MESSAGES: dict[QuotaKind, str] = {
    "upload": "Mode tamu hanya bisa mengunggah 1 buku. Masuk atau daftar untuk mengunggah lagi.",
    "session": "Mode tamu hanya bisa membuat 1 percakapan. Masuk atau daftar untuk membuat percakapan baru.",
    "generate": "Mode tamu hanya bisa membuat soal 1 kali. Masuk atau daftar untuk membuat soal lagi.",
}


def _usage(db: Session, guest_id: str) -> GuestUsage | None:
    return db.get(GuestUsage, guest_id)


def can_use(db: Session, owner: Owner, kind: QuotaKind) -> bool:
    if not owner.is_guest:
        return True
    if owner.guest_id is None:
        return False
    usage = _usage(db, owner.guest_id)
    return usage is None or getattr(usage, _COLUMNS[kind]) is None


def get_quota(db: Session, owner: Owner) -> dict[str, bool]:
    return {
        "can_upload": can_use(db, owner, "upload"),
        "can_create_session": can_use(db, owner, "session"),
        "can_generate": can_use(db, owner, "generate"),
    }


def consume(db: Session, owner: Owner, kind: QuotaKind) -> None:
    """Tandai kuota terpakai (belum di-commit). Tidak berlaku untuk akun."""
    if not owner.is_guest or owner.guest_id is None:
        return
    usage = _usage(db, owner.guest_id)
    if usage is None:
        usage = GuestUsage(guest_id=owner.guest_id)
        db.add(usage)
    setattr(usage, _COLUMNS[kind], utcnow())


def refund(db: Session, guest_id: str | None, kind: QuotaKind) -> None:
    """Kembalikan kuota bila prosesnya gagal karena sistem (belum di-commit)."""
    if not guest_id:
        return
    usage = _usage(db, guest_id)
    if usage is not None:
        setattr(usage, _COLUMNS[kind], None)
