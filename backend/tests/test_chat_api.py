"""API tests for chat generation status, message timestamps, and question filters (in-memory DB)."""

import asyncio
from contextlib import contextmanager
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import chat, questions
from app.core.database import Base
from app.main import app
from app.models.db_models import ChatSession, Document, Question
from app.services.generation import runner

GUEST_ID = "tamu-uji"
client = TestClient(app, cookies={"soalnya_guest": GUEST_ID})


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

    monkeypatch.setattr(chat, "get_session", fake_get_session)
    monkeypatch.setattr(runner, "get_session", fake_get_session)
    monkeypatch.setattr(questions, "get_session", fake_get_session)
    return fake_get_session


def _seed_session(get_session, filename="buku.pdf") -> tuple[str, str]:
    with get_session() as db:
        doc = Document(filename=filename, subject="IPAS", status="ready", guest_id=GUEST_ID)
        db.add(doc)
        db.flush()
        sess = ChatSession(document_id=doc.id, guest_id=GUEST_ID)
        db.add(sess)
        db.commit()
        return str(doc.id), str(sess.id)


def test_message_created_at_is_timezone_aware(db_factory):
    _, session_id = _seed_session(db_factory)
    client.post(f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "halo"})

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
    assert len(messages) == 2
    for m in messages:
        parsed = datetime.fromisoformat(m["created_at"].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None


def test_generation_status_lifecycle(db_factory, monkeypatch):
    _, session_id = _seed_session(db_factory)
    assert client.get(f"/api/v1/chat/sessions/{session_id}").json()["generation_status"] == "idle"

    # Tunda background task agar status 'running' bisa diamati
    real_generate = chat.background_generate_questions
    deferred = []
    monkeypatch.setattr(chat, "background_generate_questions", lambda *args: deferred.append(args))
    reply = client.post(f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "Buatkan 3 soal C2"}).json()

    detail = client.get(f"/api/v1/chat/sessions/{session_id}").json()
    assert detail["generation_status"] == "running"
    assert detail["generation_count"] == 3
    assert detail["generation_message_id"] == reply["id"]

    # Permintaan kedua selama masih berjalan tidak memulai generasi baru
    client.post(f"/api/v1/chat/sessions/{session_id}/messages", json={"content": "Buatkan 2 soal C1"})
    assert len(deferred) == 1

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            return {"finalized_questions": [{"question": "Q?", "answer": "A", "status": "final"}]}

    monkeypatch.setattr(runner, "get_aqg_graph", lambda: FakeGraph())
    asyncio.run(real_generate(*deferred[0]))
    assert client.get(f"/api/v1/chat/sessions/{session_id}").json()["generation_status"] == "done"

    class EmptyGraph:
        async def ainvoke(self, state, config=None):
            return {"finalized_questions": [], "error": "kosong"}

    monkeypatch.setattr(runner, "get_aqg_graph", lambda: EmptyGraph())
    asyncio.run(real_generate(*deferred[0]))
    listed = client.get("/api/v1/chat/sessions").json()
    assert listed[0]["generation_status"] == "failed"


def test_get_session_detail_404(db_factory):
    assert client.get("/api/v1/chat/sessions/tidak-ada").status_code == 404


def test_questions_include_document_and_filter(db_factory):
    doc_a, sess_a = _seed_session(db_factory, "buku-a.pdf")
    doc_b, sess_b = _seed_session(db_factory, "buku-b.pdf")
    with db_factory() as db:
        for sid in (sess_a, sess_b):
            db.add(Question(session_id=sid, chunk_ids="[]", question_text="Q", answer_key="A", bloom_level="C2-Memahami"))
        db.commit()

    all_qs = client.get("/api/v1/questions/").json()
    assert len(all_qs) == 2

    only_a = client.get("/api/v1/questions/", params={"document_id": doc_a}).json()
    assert len(only_a) == 1
    assert only_a[0]["session_id"] == sess_a
    assert only_a[0]["document_id"] == doc_a
    assert only_a[0]["document_filename"] == "buku-a.pdf"


def _seed_questions(get_session, session_id: str, n: int) -> list[str]:
    ids = []
    with get_session() as db:
        for i in range(n):
            q = Question(session_id=session_id, chunk_ids="[]", question_text=f"Q{i + 1}?", answer_key="A", bloom_level="C2-Memahami")
            db.add(q)
            db.flush()
            ids.append(str(q.id))
        db.commit()
    return ids


def test_question_actions_via_chat(db_factory, monkeypatch):
    from app.services.chat import handler

    _, session_id = _seed_session(db_factory)
    ids = _seed_questions(db_factory, session_id, 2)
    send = lambda text: client.post(f"/api/v1/chat/sessions/{session_id}/messages", json={"content": text}).json()  # noqa: E731

    # Out of range / missing number: the assistant asks instead of acting
    assert "tidak ada" in send("Buat ulang soal nomor 5")["content"]

    # Discussion answers synchronously about the referenced question
    seen = {}

    def fake_answer(db, number, question, history, message):
        seen["number"], seen["text"] = number, question.question_text
        return "Karena materi menyebutkannya."

    monkeypatch.setattr(handler, "answer_about_question", fake_answer)
    monkeypatch.setattr(handler, "route_message", lambda text, history, count: handler.ChatIntent(intent="discuss", question_number=2))
    assert send("Kenapa jawaban soal 2 begitu?")["content"] == "Karena materi menyebutkannya."
    assert seen == {"number": 2, "text": "Q2?"}

    # Regenerating starts one background revision of that question and marks the session running
    from app.services.chat.intent import route_message
    monkeypatch.setattr(handler, "route_message", route_message)
    jobs = []
    monkeypatch.setattr(chat, "background_revise_question", lambda *args: jobs.append(args))
    reply = send("Buat ulang soal nomor 1 jadi C4")
    assert jobs == [(session_id, ids[0], "regenerate", "C4-Menganalisis", None)]
    detail = client.get(f"/api/v1/chat/sessions/{session_id}").json()
    assert detail["generation_status"] == "running"
    assert detail["generation_count"] == 1
    assert detail["generation_message_id"] == reply["id"]

    # While it runs, another change is refused
    send("Soal nomor 2 terlalu mudah")
    assert len(jobs) == 1
