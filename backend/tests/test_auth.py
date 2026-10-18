"""API tests for login, guest mode, data ownership and guest data purge (in-memory DB)."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import auth, chat, documents, questions
from app.core.database import Base
from app.main import app
from app.models.db_models import ChatSession, Document, Question, User
from app.services.auth import data

PASSWORD = "rahasia123"


@pytest.fixture
def db_factory(monkeypatch):
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

    for module in (chat, documents, questions, auth, deps, data):
        monkeypatch.setattr(module, "get_session", fake_get_session)
    monkeypatch.setattr(data, "delete_document_vectors", lambda doc_id: None)
    return fake_get_session


def _guest(guest_id: str) -> TestClient:
    return TestClient(app, cookies={"soalnya_guest": guest_id})


def _register(client: TestClient, email: str = "budi@example.com", remember: bool = False):
    return client.post(
        "/api/v1/auth/register",
        json={"name": "Budi", "email": email, "password": PASSWORD, "remember": remember},
    )


def _seed(get_session, filename="buku.pdf", **owner) -> tuple[str, str]:
    with get_session() as db:
        doc = Document(filename=filename, subject="IPAS", status="ready", **owner)
        db.add(doc)
        db.flush()
        sess = ChatSession(document_id=doc.id, **owner)
        db.add(sess)
        db.flush()
        db.add(Question(session_id=sess.id, chunk_ids="[]", question_text="Q", answer_key="A", bloom_level="C1"))
        db.commit()
        return str(doc.id), str(sess.id)


def test_register_login_logout(db_factory):
    client = TestClient(app)
    assert client.get("/api/v1/auth/me").status_code == 401

    res = _register(client, "Budi@Example.com")
    assert res.status_code == 201
    assert res.json()["email"] == "budi@example.com"
    assert "max-age=604800" in res.headers["set-cookie"].lower()  # 7 hari tanpa "Ingat saya"
    assert client.get("/api/v1/auth/me").json()["name"] == "Budi"

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    other = TestClient(app)
    assert _register(other, "budi@example.com").status_code == 409
    bad = other.post("/api/v1/auth/login", json={"email": "budi@example.com", "password": "salah-sekali"})
    assert bad.status_code == 401
    ok = other.post("/api/v1/auth/login", json={"email": "BUDI@example.com", "password": PASSWORD, "remember": True})
    assert ok.status_code == 200
    assert "max-age=2592000" in ok.headers["set-cookie"].lower()  # 30 hari dengan "Ingat saya"


def test_register_validation(db_factory):
    client = TestClient(app)
    short = client.post("/api/v1/auth/register", json={"name": "A", "email": "a@example.com", "password": "pendek"})
    assert short.status_code == 422
    blank = client.post("/api/v1/auth/register", json={"name": "  ", "email": "a@example.com", "password": PASSWORD})
    assert blank.status_code == 422


def test_first_account_inherits_legacy_data(db_factory):
    legacy_doc, _ = _seed(db_factory)

    first = TestClient(app)
    _register(first, "pertama@example.com")
    assert [d["id"] for d in first.get("/api/v1/documents/").json()] == [legacy_doc]
    assert len(first.get("/api/v1/chat/sessions").json()) == 1
    assert len(first.get("/api/v1/questions/").json()) == 1

    second = TestClient(app)
    _register(second, "kedua@example.com")
    assert second.get("/api/v1/documents/").json() == []
    assert second.get("/api/v1/questions/").json() == []


def test_guest_data_moves_to_account_on_register(db_factory):
    _register(TestClient(app), "pertama@example.com")  # akun pertama mewarisi data lama (tidak ada)
    guest = _guest("tamu-1")
    doc_id, sess_id = _seed(db_factory, guest_id="tamu-1")
    assert len(guest.get("/api/v1/chat/sessions").json()) == 1

    res = _register(guest, "tamu@example.com")
    assert any(c.startswith("soalnya_guest=") and "Max-Age=0" in c for c in res.headers.get_list("set-cookie"))
    user_id = res.json()["id"]
    assert [s["id"] for s in guest.get("/api/v1/chat/sessions").json()] == [sess_id]
    with db_factory() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None and doc.user_id == user_id and doc.guest_id is None


def test_guest_data_moves_to_account_on_login(db_factory):
    _register(TestClient(app))
    guest = _guest("tamu-2")
    _, sess_id = _seed(db_factory, guest_id="tamu-2")
    guest.post("/api/v1/auth/login", json={"email": "budi@example.com", "password": PASSWORD})
    assert [s["id"] for s in guest.get("/api/v1/chat/sessions").json()] == [sess_id]


def test_data_is_isolated_between_owners(db_factory):
    owner = TestClient(app)
    _register(owner, "pemilik@example.com")
    user_id = owner.get("/api/v1/auth/me").json()["id"]
    doc_id, sess_id = _seed(db_factory, user_id=user_id)

    stranger = TestClient(app)
    _register(stranger, "orang-lain@example.com")
    guest = _guest("tamu-3")
    for client in (stranger, guest):
        assert client.get(f"/api/v1/chat/sessions/{sess_id}").status_code == 404
        assert client.get(f"/api/v1/chat/sessions/{sess_id}/messages").status_code == 404
        assert client.post(f"/api/v1/chat/sessions/{sess_id}/messages", json={"content": "halo"}).status_code == 404
        assert client.delete(f"/api/v1/chat/sessions/{sess_id}").status_code == 404
        assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
        assert client.delete(f"/api/v1/documents/{doc_id}").status_code == 404
        assert client.post("/api/v1/chat/sessions", json={"document_id": doc_id}).status_code == 404
        assert client.get("/api/v1/questions/").json() == []
    assert owner.get(f"/api/v1/chat/sessions/{sess_id}").status_code == 200


def test_new_guest_gets_cookie_and_owns_created_session(db_factory):
    guest = TestClient(app)
    guest.get("/api/v1/documents/")
    guest_id = guest.cookies.get("soalnya_guest")
    assert guest_id
    doc_id, _ = _seed(db_factory, guest_id=guest_id)
    created = guest.post("/api/v1/chat/sessions", json={"document_id": doc_id}).json()
    with db_factory() as db:
        sess = db.get(ChatSession, created["id"])
        assert sess is not None and sess.guest_id == guest_id and sess.user_id is None


def test_purge_stale_guest_data(db_factory):
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=30)
    stale_doc, _ = _seed(db_factory, guest_id="lama")
    fresh_doc, _ = _seed(db_factory, guest_id="baru")
    busy_doc, busy_sess = _seed(db_factory, guest_id="sibuk")
    legacy_doc, _ = _seed(db_factory)
    with db_factory() as db:
        for d in db.query(Document).filter(Document.guest_id.in_(["lama", "sibuk"])).all():
            d.last_active_at = old
        for s in db.query(ChatSession).filter(ChatSession.guest_id.in_(["lama", "sibuk"])).all():
            s.last_active_at = old
        db.get(ChatSession, busy_sess).generation_status = "running"
        db.commit()

    assert data.purge_stale_guest_data() == 1
    with db_factory() as db:
        remaining = {d.id for d in db.query(Document).all()}
        assert remaining == {fresh_doc, busy_doc, legacy_doc}
        assert db.query(ChatSession).filter(ChatSession.guest_id == "lama").count() == 0
        assert db.query(Question).count() == 3


def test_profile_password_and_delete_account(db_factory):
    client = TestClient(app)
    _register(client)
    user_id = client.get("/api/v1/auth/me").json()["id"]
    _seed(db_factory, user_id=user_id)

    assert client.patch("/api/v1/auth/me", json={"name": "Budi Santoso"}).json()["name"] == "Budi Santoso"

    wrong = client.post("/api/v1/auth/me/password", json={"current_password": "keliru", "new_password": "baru12345"})
    assert wrong.status_code == 400
    client.post("/api/v1/auth/me/password", json={"current_password": PASSWORD, "new_password": "baru12345"})
    relogin = TestClient(app).post("/api/v1/auth/login", json={"email": "budi@example.com", "password": "baru12345"})
    assert relogin.status_code == 200

    assert client.request("DELETE", "/api/v1/auth/me", json={"password": "keliru"}).status_code == 400
    assert client.request("DELETE", "/api/v1/auth/me", json={"password": "baru12345"}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    with db_factory() as db:
        assert db.query(User).count() == 0
        assert db.query(Document).count() == 0
        assert db.query(ChatSession).count() == 0
        assert db.query(Question).count() == 0
