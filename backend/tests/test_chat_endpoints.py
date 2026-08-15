"""Test script for Chat Sessions API endpoints."""
import pytest
from app.db.engine import get_session, init_db
from app.db.models import Document, ChatSession, ChatMessage
from app.api.v1.chat import list_sessions, create_new_session, delete_session
from app.schemas.api import ChatSessionCreate

def test_chat_session_flow():
    init_db()
    with get_session() as db:

        doc = db.query(Document).first()
        if not doc:
            doc = Document(id="test-doc-id", filename="test.pdf", subject="IPAS", status="ready")
            db.add(doc)
            db.commit()
            doc_id = doc.id
        else:
            doc_id = doc.id

    res = create_new_session(ChatSessionCreate(document_id=doc_id))
    assert res.id is not None
    session_id = res.id

    sessions = list_sessions(document_id=doc_id)
    assert len(sessions) > 0
    assert any(s.id == session_id for s in sessions)

    del_res = delete_session(session_id)
    assert del_res["status"] == "deleted"

def test_question_detail_used_chunks():
    import json
    from app.db.models import Question, Chunk
    from app.api.v1.questions import get_question

    init_db()
    with get_session() as db:
        doc = db.query(Document).first()
        if not doc:
            doc = Document(id="test-doc-id-2", filename="test2.pdf", subject="IPAS", status="ready")
            db.add(doc)
            db.commit()

        session = ChatSession(document_id=doc.id)
        db.add(session)
        db.commit()

        chunk = Chunk(
            document_id=doc.id,
            text="Ini adalah teks materi chunk uji coba untuk pertanyaan.",
            category="KONSEP",
            chapter="1",
            section_heading="Pengenalan",
        )
        db.add(chunk)
        db.commit()

        q = Question(
            session_id=session.id,
            chunk_ids=json.dumps([chunk.id]),
            question_type="esai",
            question_text="Apa isi materi pengenalan?",
            answer_key="Teks materi chunk uji coba.",
            bloom_level="C2-Memahami",
            status="final",
        )
        db.add(q)
        db.commit()
        q_id = q.id

    detail = get_question(q_id)
    assert detail.id == q_id
    assert len(detail.used_chunks) == 1
    assert detail.used_chunks[0].text == "Ini adalah teks materi chunk uji coba untuk pertanyaan."
    assert detail.used_chunks[0].category == "KONSEP"


if __name__ == "__main__":
    test_chat_session_flow()
    test_question_detail_used_chunks()
    print("ALL CHAT & QUESTION ENDPOINT TESTS PASSED!")

