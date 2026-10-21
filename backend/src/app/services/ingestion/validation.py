"""Reject uploads that are not usable textbooks: invalid PDFs, scans without text, and non-textbook documents."""

import io
import logging
from collections.abc import Sequence

from pydantic import BaseModel
from pypdf import PdfReader

from app.services.generation.stage_runners import invoke_json
from app.services.ingestion.chunkers.fixed_chunker import ChunkResult

logger = logging.getLogger(__name__)

MAX_UPLOAD_MB = 50
MIN_PAGES = 10
MIN_TEXT_CHARS = 3000
MIN_CHUNKS = 5
REJECT_CONFIDENCE = 0.7
SAMPLE_CHUNKS = 6
SAMPLE_CHARS = 600

SCANNED_MESSAGE = (
    "Teks tidak dapat dibaca. Kemungkinan PDF hasil scan/gambar; gunakan PDF yang teksnya bisa diseleksi."
)

SYSTEM_DOCUMENT_CHECK = (
    "Anda memeriksa apakah sebuah dokumen adalah buku pelajaran. Buku pelajaran = buku teks, modul, "
    "atau LKS untuk sekolah atau kuliah yang berisi materi pembelajaran. Novel, jurnal/artikel ilmiah, "
    "skripsi, laporan, invoice, CV, slide presentasi, atau dokumen administrasi BUKAN buku pelajaran. "
    "Jawab hanya dengan JSON."
)

DOCUMENT_CHECK_PROMPT = """Mata pelajaran yang diisi pengguna: {subject}

Cuplikan isi dokumen:
{sample}

Jawab dengan JSON:
{{"is_textbook": true/false, "confidence": 0.0-1.0, "detected_subject": "mata pelajaran yang paling sesuai dengan isi",
"subject_match": true/false (apakah isi sesuai dengan mata pelajaran yang diisi pengguna; anggap sesuai jika singkatan/sinonim, mis. IPAS = IPA),
"reason": "alasan singkat dalam bahasa Indonesia"}}"""


class DocumentRejected(Exception):
    """The upload is unusable; `user_message` is shown to the user as-is."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class DocumentCheck(BaseModel):
    is_textbook: bool = True
    confidence: float = 0.0
    detected_subject: str = ""
    subject_match: bool = True
    reason: str = ""


def validate_pdf_bytes(content: bytes) -> None:
    """Cheap synchronous checks run before the upload is stored."""
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise DocumentRejected(f"Ukuran file melebihi {MAX_UPLOAD_MB} MB.")
    if not content.startswith(b"%PDF-"):
        raise DocumentRejected("File bukan PDF yang valid.")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise DocumentRejected("PDF terkunci kata sandi. Hapus kata sandinya lalu unggah ulang.")
        page_count = len(reader.pages)
    except DocumentRejected:
        raise
    except Exception as e:
        logger.warning("Upload rejected: unreadable PDF: %s", e)
        raise DocumentRejected("PDF rusak atau tidak dapat dibaca.") from e
    if page_count < MIN_PAGES:
        raise DocumentRejected(
            f"Dokumen hanya {page_count} halaman, terlalu pendek untuk sebuah buku pelajaran (minimal {MIN_PAGES})."
        )


def check_extracted_content(chunks: Sequence[ChunkResult]) -> None:
    """A PDF whose extraction yields almost no text is a scan or image-only file."""
    total_chars = sum(len(c.text) for c in chunks)
    if len(chunks) < MIN_CHUNKS or total_chars < MIN_TEXT_CHARS:
        logger.info("[Validation] Too little text: %d chunks, %d chars", len(chunks), total_chars)
        raise DocumentRejected(SCANNED_MESSAGE)


def sample_chunks(chunks: Sequence[ChunkResult], count: int = SAMPLE_CHUNKS) -> str:
    """Evenly spread excerpts so the sample covers the whole book, not just its first chapter."""
    if not chunks:
        return ""
    step = max(1, len(chunks) // count)
    picked = list(chunks[::step])[:count]
    return "\n---\n".join(c.text[:SAMPLE_CHARS] for c in picked)


def classify_document(chunks: Sequence[ChunkResult], subject: str) -> DocumentCheck:
    """LLM check of what the document is; any failure accepts the document so an API outage never blocks uploads."""
    prompt = DOCUMENT_CHECK_PROMPT.format(subject=subject, sample=sample_chunks(chunks))
    try:
        check = DocumentCheck.model_validate(invoke_json(SYSTEM_DOCUMENT_CHECK, prompt, temperature=0.0))
    except Exception as e:
        logger.warning("[Validation] Document classification failed, accepting document: %s", e)
        return DocumentCheck()
    logger.info("[Validation] subject='%s' -> %s", subject, check.model_dump())
    return check


def check_document(chunks: Sequence[ChunkResult], subject: str) -> str | None:
    """Raise DocumentRejected for non-textbooks; return a warning when the content does not match the subject."""
    check_extracted_content(chunks)
    check = classify_document(chunks, subject)
    if not check.is_textbook and check.confidence >= REJECT_CONFIDENCE:
        reason = check.reason.strip() or "isinya tidak tampak seperti materi pembelajaran."
        raise DocumentRejected(f"File ini sepertinya bukan buku pelajaran: {reason}")
    if check.is_textbook and not check.subject_match and check.detected_subject.strip():
        return f"Isi buku tampaknya tentang {check.detected_subject.strip()}, bukan {subject}."
    return None
