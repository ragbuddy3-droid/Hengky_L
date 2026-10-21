"""API tests for the guest one-time quota: one upload, one chat session and one question generation."""

import asyncio
import io
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import auth, chat, documents
from app.core.database import Base
from app.main import app
from app.models.db_models import ChatSession, Document
from app.services.auth import data
from app.services.auth.guest_quota import GUEST_LIMIT_MESSAGES
from app.services.generation import runner


def make_pdf(pages: int = 12) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


PDF = ("buku.pdf", make_pdf(), "application/pdf")


@pytest.fixture
def db_factory(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)

    @contextmanager
    def fake_get_session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    for module in (chat, documents, auth, deps, data, runner):
        monkeypatch.setattr(module, "get_session", fake_get_session)
    monkeypatch.setattr(data, "delete_document_vectors", lambda doc_id: None)
    monkeypatch.setattr(documents, "process_document", lambda *args: None)
    monkeypatch.setattr(documents, "_RAW_DATA_DIR", tmp_path)
    return fake_get_session


@pytest.fixture
def deferred(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(chat, "background_generate_questions", lambda *args: calls.append(args))
    return calls


def _guest(guest_id: str = "tamu-kuota") -> TestClient:
    return TestClient(app, cookies={"soalnya_guest": guest_id})


def _upload(client: TestClient):
    return client.post("/api/v1/documents/", files={"file": PDF}, data={"subject": "IPAS"})


def _ready_document(get_session, doc_id: str) -> None:
    with get_session() as db:
        db.query(Document).filter(Document.id == doc_id).update({Document.status: "ready"})
        db.commit()


def test_guest_can_upload_only_once_even_after_delete(db_factory):
    client = _guest()
    assert client.get("/api/v1/auth/quota").json()["can_upload"] is True

    doc_id = _upload(client).json()["id"]
    assert client.get("/api/v1/auth/quota").json()["can_upload"] is False

    second = _upload(client)
    assert second.status_code == 403
    assert second.json()["detail"] == GUEST_LIMIT_MESSAGES["upload"]

    assert client.delete(f"/api/v1/documents/{doc_id}").status_code == 200
    assert _upload(client).status_code == 403


def test_guest_can_create_only_one_session(db_factory):
    client = _guest()
    doc_id = _upload(client).json()["id"]
    _ready_document(db_factory, doc_id)

    session_id = client.post("/api/v1/chat/sessions", json={"document_id": doc_id}).json()["id"]
    second = client.post("/api/v1/chat/sessions", json={"document_id": doc_id})
    assert second.status_code == 403
    assert second.json()["detail"] == GUEST_LIMIT_MESSAGES["session"]

    client.delete(f"/api/v1/chat/sessions/{session_id}")
    assert client.post("/api/v1/chat/sessions", json={"document_id": doc_id}).status_code == 403


def test_guest_can_generate_only_once(db_factory, deferred):
    client = _guest()
    doc_id = _upload(client).json()["id"]
    _ready_document(db_factory, doc_id)
    session_id = client.post("/api/v1/chat/sessions", json={"document_id": doc_id}).json()["id"]
    url = f"/api/v1/chat/sessions/{session_id}/messages"

    client.post(url, json={"content": "Buatkan 3 soal C2"})
    assert len(deferred) == 1
    with db_factory() as db:
        db.query(ChatSession).filter(ChatSession.id == session_id).update({ChatSession.generation_status: "done"})
        db.commit()

    # Pesan biasa tetap boleh, permintaan soal kedua ditolak lewat balasan chat
    assert client.post(url, json={"content": "halo"}).status_code == 200
    reply = client.post(url, json={"content": "Buatkan 2 soal C1"}).json()
    assert reply["content"] == GUEST_LIMIT_MESSAGES["generate"]
    assert len(deferred) == 1
    assert client.get(f"/api/v1/chat/sessions/{session_id}").json()["generation_status"] == "done"


def test_failed_generation_refunds_guest_quota(db_factory, deferred, monkeypatch):
    client = _guest()
    doc_id = _upload(client).json()["id"]
    _ready_document(db_factory, doc_id)
    session_id = client.post("/api/v1/chat/sessions", json={"document_id": doc_id}).json()["id"]
    client.post(f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "Buatkan 3 soal C2"})
    assert client.get("/api/v1/auth/quota").json()["can_generate"] is False

    class EmptyGraph:
        async def ainvoke(self, state, config=None):
            return {"finalized_questions": [], "error": "kosong"}

    monkeypatch.setattr(runner, "get_aqg_graph", lambda: EmptyGraph())
    asyncio.run(runner.background_generate_questions(*deferred[0]))
    assert client.get("/api/v1/auth/quota").json()["can_generate"] is True


def test_logged_in_user_is_not_limited(db_factory):
    client = TestClient(app)
    client.post(
        "/api/v1/auth/register",
        json={"name": "Budi", "email": "budi@example.com", "password": "rahasia123", "remember": False},
    )
    assert _upload(client).status_code == 200
    doc_id = _upload(client).json()["id"]
    _ready_document(db_factory, doc_id)
    for _ in range(2):
        assert client.post("/api/v1/chat/sessions", json={"document_id": doc_id}).status_code == 200
    assert client.get("/api/v1/auth/quota").json() == {
        "can_upload": True,
        "can_create_session": True,
        "can_generate": True,
    }


def test_quota_is_per_guest(db_factory):
    _upload(_guest("tamu-a"))
    assert _upload(_guest("tamu-b")).status_code == 200
