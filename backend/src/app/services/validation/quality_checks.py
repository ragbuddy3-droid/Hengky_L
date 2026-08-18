"""Post-generation quality heuristic checks (non-LLM)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_answer_quality(question: dict[str, Any]) -> list[str]:
    """Check answer quality heuristics. Returns list of issue descriptions."""
    issues: list[str] = []
    answer = question.get("answer", "")
    q_type = question.get("question_type", "esai")

    word_count = len(answer.split()) if answer else 0
    if q_type == "isian_singkat" and word_count > 25:
        issues.append(f"Jawaban isian_singkat terlalu panjang ({word_count} kata, max 25)")
    if q_type in ("esai", "esai_pendek") and word_count < 5:
        issues.append(f"Jawaban esai terlalu pendek ({word_count} kata, min 5)")

    rubric = question.get("rubric", [])
    if isinstance(rubric, list) and len(rubric) < 3:
        issues.append(f"Rubrik hanya {len(rubric)} tingkat, minimum 3")

    q_text = question.get("question", "")
    if q_text and not q_text.strip().endswith(("?", "!")):
        issues.append("Pertanyaan tidak diakhiri tanda tanya atau seru")

    return issues
