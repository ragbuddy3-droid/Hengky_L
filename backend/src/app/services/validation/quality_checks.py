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
    if q_text.count("?") >= 2:
        return "Soal berisi lebih dari satu pertanyaan. Ajukan SATU pertanyaan saja per butir soal."
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

    # Check if answer is essentially identical to question (high word overlap)
    if q_text and answer:
        q_words = set(q_text.lower().split())
        a_words = set(answer.lower().split())
        if q_words and a_words:
            overlap = len(q_words & a_words) / max(len(q_words), len(a_words))
            if overlap > 0.85:
                issues.append("Jawaban terlalu mirip dengan teks pertanyaan (overlap > 85%)")

    return issues
