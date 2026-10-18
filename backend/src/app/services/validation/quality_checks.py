"""Post-generation quality heuristic checks (non-LLM)."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Imperative essay prompts ("Jelaskan ...", "Sebutkan ...") may legitimately end with a period.
_IMPERATIVE_VERBS = (
    "jelaskan", "sebutkan", "tuliskan", "uraikan", "coba", "bandingkan", "berikan",
    "tentukan", "ceritakan", "identifikasi", "analisislah", "analisis", "deskripsikan",
    "ramalkan", "perkirakan",
)

# Questions that lean on the student's classroom experience instead of the book content
# are ambiguous for anyone who did not attend that lesson.
VAGUE_REFERENCE_PATTERNS = [
    r"(?:sudah|telah)\s+(?:kamu|kalian)\s+(?:pelajari|lakukan|praktikkan|mainkan|coba)",
    r"(?:kamu|kalian)\s+(?:sudah|telah)\s+(?:pelajari|lakukan|praktikkan|mainkan|coba)",
    r"(?:dipelajari|dilakukan|dipraktikkan|dimainkan)\s+di\s+kelas",
    r"\bdi\s+sekolah(?:mu|\s+kalian)\b",
    r"\baktivitas\s+tadi\b",
    r"\byang\s+(?:kamu|kalian)\s+(?:mainkan|pelajari)\b",
]

# Students only see the question, never the source text, so "menurut teks" points at nothing
TEXT_REFERENCE_PATTERNS = [
    r"\b(?:dalam|pada|di|menurut|berdasarkan|dari)\s+(?:teks|bacaan|wacana|materi|buku|konteks)(?:\s+(?:ini|tersebut|di\s*atas))?\b",
    r"\byang\s+(?:disebutkan|dijelaskan|tertulis|dibahas|diceritakan)\s+(?:dalam|pada|di)\b",
]

# An expected answer saying the information is missing means the question asks for something the material lacks
UNANSWERABLE_ANSWER_PATTERNS = [
    r"^\W*(?:tidak|belum)\s+(?:disebutkan|dijelaskan|diketahui|tertulis|dicantumkan|ada\s+(?:informasi|keterangan|data))",
    r"\b(?:tidak|belum)\s+(?:disebutkan|dijelaskan|tertulis|dicantumkan)\s+(?:secara\s+\w+\s+)?(?:dalam|di|pada)\s+(?:teks|materi|bacaan|konteks|buku)",
    r"\b(?:teks|materi|bacaan|konteks)\s+(?:tidak|tidak\s+pernah)\s+(?:menyebutkan|menjelaskan|mencantumkan)",
]

# Reflective / meta-learning questions ask about the lesson itself, not the book content
REFLECTIVE_PATTERNS = [
    r"setelah mempelajari bab ini",
    r"tujuan pembelajaran",
    r"apa yang (?:sudah|telah) (?:kamu|kalian) pelajari",
    r"apa yang dapat kamu (?:lakukan|capai|raih)",
    r"apa yang perlu kamu lakukan untuk (?:mengetahui|memahami)",
    r"apa yang (?:kamu|kalian) (?:ketahui|pahami) tentang bab",
    r"apa manfaat mempelajari",
    r"mengapa kita perlu belajar",
    r"apa yang bisa kamu pelajari",
    r"apa yang ingin kamu ketahui",
]


def tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def is_reflective_question(question_text: str) -> bool:
    """Check if the question matches reflective / meta-learning patterns."""
    text_lower = question_text.lower().strip()
    return any(re.search(pattern, text_lower) for pattern in REFLECTIVE_PATTERNS)


def deduplicate_questions(
    questions: list[dict[str, Any]],
    threshold: float = 0.70,
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Drop questions whose token overlap with an earlier (or already accepted `existing`) one reaches `threshold`."""
    seen = [tokens(e.get("question", "")) for e in (existing or [])]
    unique: list[dict[str, Any]] = []
    for cand in questions:
        c_tokens = tokens(cand.get("question", ""))
        if not any(jaccard(c_tokens, s) >= threshold for s in seen):
            unique.append(cand)
            seen.append(c_tokens)
    return unique


def _last_sentence(text: str) -> str:
    parts = [p.strip() for p in re.split(r"[.?!]+", text) if p.strip()]
    return parts[-1] if parts else ""


def has_valid_question_ending(q_text: str) -> bool:
    """A question ends with ?/! or is an imperative instruction ending with a period."""
    text = q_text.strip()
    if text.endswith(("?", "!")):
        return True
    if text.endswith("."):
        return _last_sentence(text).lower().startswith(_IMPERATIVE_VERBS)
    return False


def find_clarity_issue(q_text: str) -> str | None:
    """Return a feedback message if the question is ambiguous for a student reading it cold."""
    text = q_text.lower()
    if any(re.search(p, text) for p in VAGUE_REFERENCE_PATTERNS):
        return (
            "Soal merujuk pengalaman kelas (mis. 'yang telah kamu pelajari/lakukan'). "
            "Tulis soal yang mandiri: sebut langsung konsep/objek dari materi buku."
        )
    if any(re.search(p, text) for p in TEXT_REFERENCE_PATTERNS):
        return (
            "Soal merujuk teks/bacaan (mis. 'yang disebutkan dalam teks'), padahal siswa tidak melihat teksnya. "
            "Tanyakan fakta atau konsepnya secara langsung."
        )
    if q_text.count("?") >= 2:
        return "Soal berisi lebih dari satu pertanyaan. Ajukan SATU pertanyaan saja per butir soal."
    return None


def find_unanswerable_answer(answer: str) -> str | None:
    """Return a feedback message if the expected answer admits the material does not contain it."""
    text = answer.lower().strip()
    if any(re.search(p, text) for p in UNANSWERABLE_ANSWER_PATTERNS):
        return (
            "Jawaban ideal menyatakan informasinya tidak ada di materi, jadi soal tidak dapat dijawab. "
            "Ganti dengan pertanyaan tentang fakta yang benar-benar tertulis di materi."
        )
    return None


def validate_answer_quality(question: dict[str, Any]) -> list[str]:
    """Check answer quality heuristics. Returns list of issue descriptions."""
    issues: list[str] = []
    answer = question.get("answer") or question.get("expected_answer", "")
    q_type = question.get("question_type", "esai")
    q_text = question.get("question", "")

    word_count = len(answer.split()) if answer else 0
    if q_type == "isian_singkat" and word_count > 25:
        issues.append(f"Jawaban isian_singkat terlalu panjang ({word_count} kata, max 25)")
    if q_type in ("esai", "esai_pendek") and word_count < 5:
        issues.append(f"Jawaban esai terlalu pendek ({word_count} kata, min 5)")

    if q_text and not has_valid_question_ending(q_text):
        issues.append("Pertanyaan tidak diakhiri tanda tanya atau seru")

    if q_text and len(q_text.strip()) < 10:
        issues.append(f"Pertanyaan terlalu pendek ({len(q_text.strip())} karakter)")

    clarity_issue = find_clarity_issue(q_text) if q_text else None
    if clarity_issue:
        issues.append(clarity_issue)
    unanswerable = find_unanswerable_answer(answer) if answer else None
    if unanswerable:
        issues.append(unanswerable)

    # Check if answer is essentially identical to question (high word overlap)
    if q_text and answer:
        q_words = set(q_text.lower().split())
        a_words = set(answer.lower().split())
        if q_words and a_words:
            overlap = len(q_words & a_words) / max(len(q_words), len(a_words))
            if overlap > 0.85:
                issues.append("Jawaban terlalu mirip dengan teks pertanyaan (overlap > 85%)")

    return issues
