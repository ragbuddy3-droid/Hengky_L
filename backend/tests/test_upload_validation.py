"""Tests for rejecting uploads that are not usable textbooks."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_guest_quota import db_factory, make_pdf  # noqa: F401  (fixture re-export)

from app.core.config import get_settings
from app.main import app
from app.models.db_models import Chunk, Document
from app.services.generation import stage_runners
from app.services.ingestion import pipeline
from app.services.ingestion.chunkers.fixed_chunker import ChunkResult
from app.services.ingestion.validation import DocumentRejected, check_document, check_upload_size, validate_pdf_bytes


def _chunks(count: int = 8, size: int = 800) -> list[ChunkResult]:
    return [ChunkResult(text="Fotosintesis adalah proses tumbuhan. " * (size // 37), category="materi_pokok")
            for _ in range(count)]


def _fake_model(monkeypatch, answer: dict | Exception):
    class FakeModel:
        def invoke(self, messages):
            if isinstance(answer, Exception):
                raise answer
            return SimpleNamespace(content=json.dumps(answer))

    monkeypatch.setattr(stage_runners, "get_chat_model", lambda **kwargs: FakeModel())


def _upload(client: TestClient, content: bytes):
    return client.post("/api/v1/documents/", files={"file": ("buku.pdf", content, "application/pdf")},
                       data={"subject": "IPAS"})


@pytest.mark.parametrize(("content", "message"), [
    (b"bukan pdf sama sekali", "File bukan PDF yang valid."),
    (b"%PDF-1.4 rusak", "PDF rusak atau tidak dapat dibaca."),
    (make_pdf(3), "terlalu pendek"),
])
def test_invalid_pdf_is_rejected_without_using_guest_quota(db_factory, content, message):  # noqa: F811
    client = TestClient(app, cookies={"soalnya_guest": "tamu-validasi"})
    res = _upload(client, content)
    assert res.status_code == 400
    assert message in res.json()["detail"]
    assert client.get("/api/v1/auth/quota").json()["can_upload"] is True


def test_valid_pdf_passes_sync_checks():
    validate_pdf_bytes(make_pdf(12))


def test_scanned_pdf_is_rejected():
    with pytest.raises(DocumentRejected, match="scan"):
        check_document([ChunkResult(text="", category="materi_pokok")], "IPAS")


def test_non_textbook_is_rejected(monkeypatch):
    _fake_model(monkeypatch, {"is_textbook": False, "confidence": 0.9, "reason": "Ini novel fiksi."})
    with pytest.raises(DocumentRejected, match="bukan buku pelajaran: Ini novel fiksi."):
        check_document(_chunks(), "IPAS")


def test_low_confidence_non_textbook_is_accepted(monkeypatch):
    _fake_model(monkeypatch, {"is_textbook": False, "confidence": 0.4})
    assert check_document(_chunks(), "IPAS") is None


def test_subject_mismatch_only_warns(monkeypatch):
    _fake_model(monkeypatch, {"is_textbook": True, "confidence": 0.95, "detected_subject": "Biologi",
                              "subject_match": False})
    assert check_document(_chunks(), "Matematika") == "Isi buku tampaknya tentang Biologi, bukan Matematika."


def test_llm_failure_accepts_document(monkeypatch):
    _fake_model(monkeypatch, TimeoutError("api down"))
    assert check_document(_chunks(), "IPAS") is None


def test_pipeline_rejection_refunds_quota_and_stores_nothing(db_factory, monkeypatch):  # noqa: F811
    client = TestClient(app, cookies={"soalnya_guest": "tamu-novel"})
    doc_id = _upload(client, make_pdf(12)).json()["id"]
    assert client.get("/api/v1/auth/quota").json()["can_upload"] is False

    indexed: list = []
    monkeypatch.setattr(pipeline, "extract_pages_from_pdf", lambda path: ["halaman"])
    monkeypatch.setattr(pipeline, "chunk_pages", lambda pages: _chunks())
    monkeypatch.setattr(pipeline, "get_shared_dense_index", lambda: SimpleNamespace(index_chunks=indexed.append))
    _fake_model(monkeypatch, {"is_textbook": False, "confidence": 0.9, "reason": "Ini invoice."})

    pipeline.process_document(doc_id, "unused.pdf")

    with db_factory() as db:
        doc = db.get(Document, doc_id)
        assert doc.status == "failed"
        assert doc.error_message == "File ini sepertinya bukan buku pelajaran: Ini invoice."
        assert db.query(Chunk).filter(Chunk.document_id == doc_id).count() == 0
    assert indexed == []
    assert client.get("/api/v1/auth/quota").json()["can_upload"] is True


@pytest.mark.parametrize("filename", [r"..\..\evil.pdf", "../../evil.pdf", r"C:\Windows\evil.pdf"])
def test_upload_filename_cannot_leave_raw_dir(db_factory, filename):  # noqa: F811
    client = TestClient(app, cookies={"soalnya_guest": f"tamu-{len(filename)}"})
    res = client.post("/api/v1/documents/", files={"file": (filename, make_pdf(12), "application/pdf")},
                      data={"subject": "IPAS"})
    with db_factory() as db:
        path = Path(db.get(Document, res.json()["id"]).filepath)
    assert path.parent == get_settings().paths.raw_dir
    assert path.name.endswith("_evil.pdf")


def test_upload_size_is_checked_before_reading():
    with pytest.raises(DocumentRejected, match="melebihi"):
        check_upload_size(51 * 1024 * 1024)
    check_upload_size(None)


def test_document_deleted_during_processing_leaves_no_chunks(db_factory, monkeypatch):  # noqa: F811
    client = TestClient(app, cookies={"soalnya_guest": "tamu-hapus"})
    doc_id = _upload(client, make_pdf(12)).json()["id"]

    def index_then_user_deletes(rows):
        assert client.delete(f"/api/v1/documents/{doc_id}").status_code == 200

    removed: list[str] = []
    monkeypatch.setattr(pipeline, "extract_pages_from_pdf", lambda path: ["halaman"])
    monkeypatch.setattr(pipeline, "chunk_pages", lambda pages: _chunks())
    monkeypatch.setattr(pipeline, "get_shared_dense_index", lambda: SimpleNamespace(index_chunks=index_then_user_deletes))
    monkeypatch.setattr(pipeline, "delete_document_vectors", removed.append)
    _fake_model(monkeypatch, {"is_textbook": True, "confidence": 0.9})

    pipeline.process_document(doc_id, "unused.pdf")

    with db_factory() as db:
        assert db.query(Chunk).filter(Chunk.document_id == doc_id).count() == 0
    assert removed == [doc_id]
