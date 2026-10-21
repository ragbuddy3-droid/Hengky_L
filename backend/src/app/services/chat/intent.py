"""Route chat messages: regex for the clear cases (generation, actions on a numbered question, greetings), LLM for the rest."""

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, field_validator

from app.schemas.api_schemas import GenerateParams
from app.services.chat.prompts import ROUTER_PROMPT, SYSTEM_ROUTER_PERSONA
from app.services.generation.planner import MIXED_BLOOM_LEVELS
from app.services.generation.stage_runners import invoke_json

if TYPE_CHECKING:
    from app.models.db_models import ChatMessage

logger = logging.getLogger(__name__)

# SD only covers C1-C4; C5/C6 in a message are ignored (falls back to mixed levels)
BLOOM_MAPPING = {level[:2]: level for level in MIXED_BLOOM_LEVELS}

MAX_QUESTIONS_PER_REQUEST = 20
DEFAULT_NUM_QUESTIONS = 5

IntentName = Literal["generate", "regenerate", "revise", "discuss", "help", "out_of_scope"]

# "soal nomor 3", "soal no. 3", "soal ke-3", "soal #3", "soal 3"
_QUESTION_NUMBER = re.compile(r'\bsoal\s*(?:nomor|nmr|no\.?|ke-?|#)?\s*(\d+)\b', re.IGNORECASE)
_REGENERATE_VERBS = re.compile(
    r'\b(?:buat(?:kan)?\s*ulang|bikin(?:kan)?\s*ulang|generate\s*ulang|regenerate|ulangi|ganti(?:kan)?|tukar)\b', re.IGNORECASE,
)
_REVISE_VERBS = re.compile(
    r'\b(?:ubah|revisi|perbaiki|perjelas|perbarui|jadikan|sederhanakan|persingkat|perpanjang|persulit|permudah'
    r'|terlalu\s+\w+|kurang\s+\w+|salah|tidak\s+(?:jelas|sesuai|tepat))\b',
    re.IGNORECASE,
)
_DISCUSS_WORDS = re.compile(
    r'\b(?:kenapa|mengapa|jelaskan|terangkan|bahas|apa|apakah|bagaimana|maksud(?:nya)?|halaman|sumber(?:nya)?|dari\s+mana)\b',
    re.IGNORECASE,
)
_GREETING = re.compile(
    r'^\s*(?:halo|hai|hi|hello|hey|pagi|siang|sore|malam|selamat\s+\w+|terima\s*kasih|makasih|thanks?|thank\s+you'
    r'|ok(?:e|ay)?|sip|mantap|bisa\s+apa(?:\s+saja)?|apa\s+saja\s+yang\s+bisa\s+\w+|bantuan|help)\b[\s\w!?.,]*$',
    re.IGNORECASE,
)


class ChatIntent(BaseModel):
    """Routed meaning of a chat message."""

    intent: IntentName = "help"
    question_number: int | None = None
    bloom_level: str | None = None  # full label, e.g. "C4-Menganalisis"
    instruction: str | None = None

    @field_validator("bloom_level", mode="before")
    @classmethod
    def _normalize_level(cls, value: object) -> str | None:
        match = re.search(r'C[1-4]', str(value or ""), re.IGNORECASE)
        return BLOOM_MAPPING.get(match.group(0).upper()) if match else None

    @field_validator("question_number", mode="before")
    @classmethod
    def _to_int(cls, value: object) -> int | None:
        try:
            return int(value) if value not in (None, "", "null") else None  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return None


def _bloom_in(text: str) -> str | None:
    match = re.search(r'\b(C[1-4])\b', text, re.IGNORECASE)
    return BLOOM_MAPPING.get(match.group(1).upper()) if match else None


def is_generation_intent(text: str) -> bool:
    """Whether the message asks for questions to be generated."""
    if not text:
        return False
    t = text.lower().strip()

    # 1. Generation verb followed by a question noun: "buatkan 3 soal", "tolong bikin pertanyaan"
    if re.search(r'\b(?:buat(?:kan)?|bikin|generate|minta|tulis(?:kan)?|susun|ciptakan|tolong)\b.*\b(?:soal|pertanyaan|latihan|kuis|ujian)\b', t):
        return True

    # 2. Number + question noun: "3 soal", "10 soal esai"
    if re.search(r'\b\d+\s*(?:soal|pertanyaan|latihan|kuis)\b', t):
        return True

    # 3. Bloom level code with an educational keyword: "soal c2", "c4 bab 3"
    if re.search(r'\b(c[1-4])\b', t) and any(w in t for w in ['soal', 'bab', 'esai', 'isian', 'buat', 'materi', 'level']):
        return True

    # 4. Question type with generation/chapter context
    if any(q_type in t for q_type in ['esai', 'isian singkat', 'isian', 'pilihan ganda']) and any(
        w in t for w in ['buat', 'bikin', 'bab', 'soal', 'minta', 'tolong']
    ):
        return True

    # 5. Question noun + topic/chapter/level
    return bool(
        any(w in t for w in ['soal', 'pertanyaan'])
        and any(w in t for w in ['bab', 'materi', 'tema', 'c1', 'c2', 'c3', 'c4', 'tingkat', 'level'])
    )


def parse_generation_params(text: str) -> GenerateParams:
    """Extract number of questions, Bloom level and chapter from a natural-language request."""
    num_questions = DEFAULT_NUM_QUESTIONS
    chapter = None

    match_num = re.search(r'(\d+)\s*(?:soal|pertanyaan)', text, re.IGNORECASE)
    if match_num:
        num_questions = max(1, min(MAX_QUESTIONS_PER_REQUEST, int(match_num.group(1))))

    bloom_level = _bloom_in(text)

    match_chap = re.search(r'\bbab\s*([\w]+|[IVXLCDM]+)', text, re.IGNORECASE)
    if match_chap:
        chapter = match_chap.group(1)

    logger.debug("Parsed generation params: num_questions=%d, bloom_level=%s, chapter=%s", num_questions, bloom_level, chapter)
    return GenerateParams(num_questions=num_questions, chapter=chapter, bloom_level=bloom_level)


def parse_question_action(text: str) -> ChatIntent | None:
    """Regex route for a message about one numbered question ("buat ulang soal nomor 3", "soal 2 jadikan C4").

    Checked before `is_generation_intent`, which would also match "buat ulang soal 3". Returns None when the
    message names no question number, or names one without a clear action or question word (left to the LLM router).
    """
    if not text or re.search(r'\b\d+\s*(?:soal|pertanyaan)\b', text, re.IGNORECASE):
        return None  # "Buatkan 3 soal ..." asks for new questions
    match = _QUESTION_NUMBER.search(text)
    if not match:
        return None
    number = int(match.group(1))
    level = _bloom_in(text)

    # A new level changes the cognitive plan, so the question is generated again rather than patched
    if _REGENERATE_VERBS.search(text) or (level and _REVISE_VERBS.search(text)):
        return ChatIntent(intent="regenerate", question_number=number, bloom_level=level)
    if _REVISE_VERBS.search(text):
        return ChatIntent(intent="revise", question_number=number, instruction=text.strip())
    if _DISCUSS_WORDS.search(text):
        return ChatIntent(intent="discuss", question_number=number)
    return None


def is_greeting(text: str) -> bool:
    """Short greetings / thanks / "bisa apa?" that only need the help reply."""
    return bool(text) and len(text) <= 60 and bool(_GREETING.match(text))


def route_message(text: str, history: "Sequence[ChatMessage]", question_count: int) -> ChatIntent:
    """Regex first (numbered-question actions, generation requests, greetings); the LLM router only for the rest."""
    if action := parse_question_action(text):
        return action
    if is_generation_intent(text):
        return ChatIntent(intent="generate")
    if is_greeting(text):
        return ChatIntent(intent="help")
    return classify_message(text, history, question_count)


def format_history(history: "Sequence[ChatMessage]", max_chars: int = 400) -> str:
    lines = []
    for m in history:
        content = str(m.content)
        if len(content) > max_chars:
            content = content[:max_chars] + "…"
        lines.append(f"{'Pengguna' if str(m.role) == 'user' else 'Asisten'}: {content}")
    return "\n".join(lines) or "(kosong)"


def classify_message(text: str, history: "Sequence[ChatMessage]", question_count: int) -> ChatIntent:
    """LLM router for messages the regexes did not catch; any failure falls back to the help reply."""
    prompt = ROUTER_PROMPT.format(question_count=question_count, history=format_history(history), message=text)
    try:
        intent = ChatIntent.model_validate(invoke_json(SYSTEM_ROUTER_PERSONA, prompt, temperature=0.0))
    except Exception as e:
        logger.warning("[Chat Router] classification failed, falling back to help: %s", e)
        return ChatIntent(intent="help")
    if intent.intent == "revise" and not intent.instruction:
        intent.instruction = text.strip()
    logger.info("[Chat Router] '%s' -> %s", text[:60], intent.model_dump())
    return intent
