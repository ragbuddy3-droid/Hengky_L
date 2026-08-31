"""Post-generation quality heuristic checks (non-LLM)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


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

    if q_text and not q_text.strip().endswith(("?", "!")):
        issues.append("Pertanyaan tidak diakhiri tanda tanya atau seru")

    if q_text and len(q_text.strip()) < 10:
        issues.append(f"Pertanyaan terlalu pendek ({len(q_text.strip())} karakter)")

    # Check if answer is essentially identical to question (high word overlap)
    if q_text and answer:
        q_words = set(q_text.lower().split())
        a_words = set(answer.lower().split())
        if q_words and a_words:
            overlap = len(q_words & a_words) / max(len(q_words), len(a_words))
            if overlap > 0.85:
                issues.append("Jawaban terlalu mirip dengan teks pertanyaan (overlap > 85%)")

    return issues
