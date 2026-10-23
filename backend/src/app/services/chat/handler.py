"""Turn one user chat message into the assistant's reply and, for long work, a background job to start."""

import logging
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.db_models import ChatMessage, ChatSession, Question
from app.services.auth.guest_quota import GUEST_LIMIT_MESSAGES, can_use, consume
from app.services.auth.owner import Owner
from app.services.chat.discussion import answer_about_question
from app.services.chat.intent import ChatIntent, parse_generation_params, route_message
from app.services.chat.state_manager import ChatStateManager

logger = logging.getLogger(__name__)

MAX_REVISIONS_PER_QUESTION = 3

EXAMPLES = (
    "- **Buat soal:** \"Buatkan 5 soal C3 bab 2\"\n"
    "- **Bahas soal:** \"Kenapa jawaban soal nomor 1 seperti itu?\"\n"
    "- **Buat ulang soal:** \"Buat ulang soal nomor 2 jadi C4\"\n"
    "- **Revisi soal:** \"Soal nomor 3 terlalu mudah\""
)
HELP_REPLY = "Halo! Saya bisa membantu membuat dan mengelola soal dari dokumen ini. Contohnya:\n\n" + EXAMPLES
OUT_OF_SCOPE_REPLY = (
    "Maaf, saya hanya bisa membantu hal yang berkaitan dengan soal dari dokumen ini, "
    "jadi pertanyaan tersebut di luar cakupan saya. Anda bisa mencoba:\n\n" + EXAMPLES
)
GENERATION_RUNNING_REPLY = "Soal sebelumnya masih diproses. Mohon tunggu hingga selesai sebelum meminta perubahan baru."

JobKind = Literal["generate", "revise"]


@dataclass
class ChatReply:
    message: ChatMessage
    job: tuple[JobKind, tuple[Any, ...]] | None = None  # background job for the endpoint to schedule


def _start_background(db: Session, session_id: str, manager: ChatStateManager, text: str, count: int) -> ChatMessage | None:
    """Mark the session as running and post the "please wait" message before the job starts (no 'idle' gap for polling).

    Returns None when another request already started a job: the conditional UPDATE lets only one of two
    simultaneous requests through.
    """
    started = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.generation_status != "running")
        .update({ChatSession.generation_status: "running", ChatSession.generation_count: count})
    )
    if not started:
        return None
    bot_msg = manager.add_message("assistant", text)
    db.query(ChatSession).filter(ChatSession.id == session_id).update({ChatSession.generation_message_id: bot_msg.id})
    return bot_msg


def _generate(db: Session, session: ChatSession, owner: Owner, manager: ChatStateManager, intent: ChatIntent, content: str) -> ChatReply:
    if session.generation_status == "running":
        return ChatReply(manager.add_message("assistant", GENERATION_RUNNING_REPLY))
    if not can_use(db, owner, "generate"):
        return ChatReply(manager.add_message("assistant", GUEST_LIMIT_MESSAGES["generate"]))
    params = parse_generation_params(content)
    if not params.bloom_level and intent.bloom_level:
        params.bloom_level = intent.bloom_level
    bot_msg = _start_background(
        db, session.id, manager,
        f"Sedang membuat {params.num_questions} soal ({params.bloom_level or 'Beragam Level'}). Mohon tunggu sebentar...",
        params.num_questions,
    )
    if bot_msg is None:
        return ChatReply(manager.add_message("assistant", GENERATION_RUNNING_REPLY))
    consume(db, owner, "generate")
    return ChatReply(bot_msg, ("generate", (session.id, content, params)))


def _missing_number_reply(intent: ChatIntent, count: int) -> str | None:
    if count == 0:
        return "Belum ada soal di sesi ini. Buat soal terlebih dahulu, misalnya \"Buatkan 5 soal C2\"."
    if intent.question_number is None:
        return f"Soal nomor berapa yang Anda maksud? Sesi ini memiliki {count} soal (nomor 1–{count})."
    if not 1 <= intent.question_number <= count:
        return f"Soal nomor {intent.question_number} tidak ada. Sesi ini memiliki {count} soal (nomor 1–{count})."
    return None


def _change_question(
    db: Session, session: ChatSession, manager: ChatStateManager, intent: ChatIntent, number: int, question: Question,
) -> ChatReply:
    if session.generation_status == "running":
        return ChatReply(manager.add_message("assistant", GENERATION_RUNNING_REPLY))
    if (question.revision_count or 0) >= MAX_REVISIONS_PER_QUESTION:
        return ChatReply(manager.add_message(
            "assistant",
            f"Soal #{number} sudah diperbarui {MAX_REVISIONS_PER_QUESTION} kali, batas maksimum per soal. "
            "Silakan minta soal baru, misalnya \"Buatkan 1 soal C3\".",
        ))
    level = intent.bloom_level if intent.intent == "regenerate" else None
    verb = "Membuat ulang" if intent.intent == "regenerate" else "Merevisi"
    target = f" menjadi {level}" if level else ""
    bot_msg = _start_background(db, session.id, manager, f"{verb} Soal #{number}{target}. Mohon tunggu sebentar...", 1)
    if bot_msg is None:
        return ChatReply(manager.add_message("assistant", GENERATION_RUNNING_REPLY))
    return ChatReply(bot_msg, ("revise", (session.id, question.id, intent.intent, level, intent.instruction)))


def handle_message(db: Session, session: ChatSession, owner: Owner, content: str) -> ChatReply:
    """Store the user's message, route it, and return the assistant's reply (plus a background job, if any)."""
    manager = ChatStateManager(session.id, db)
    history = manager.recent_history()
    manager.add_message("user", content)
    db.commit()

    questions = manager.questions()
    intent = route_message(content, history, len(questions))
    logger.info("[Chat] session='%s' intent=%s number=%s", session.id, intent.intent, intent.question_number)

    if intent.intent == "generate":
        return _generate(db, session, owner, manager, intent, content)
    if intent.intent in ("regenerate", "revise", "discuss"):
        if reply := _missing_number_reply(intent, len(questions)):
            return ChatReply(manager.add_message("assistant", reply))
        number = intent.question_number or 0
        question = questions[number - 1]
        if intent.intent == "discuss":
            return ChatReply(manager.add_message("assistant", answer_about_question(db, number, question, history, content)))
        return _change_question(db, session, manager, intent, number, question)
    if intent.intent == "out_of_scope":
        return ChatReply(manager.add_message("assistant", OUT_OF_SCOPE_REPLY))
    return ChatReply(manager.add_message("assistant", HELP_REPLY))
