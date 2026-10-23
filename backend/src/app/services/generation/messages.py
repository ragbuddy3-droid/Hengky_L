"""Markdown chat messages that report generation and revision results."""

from typing import Any


def _format_question(number: int, q: dict[str, Any]) -> str:
    parts = [
        f"### Soal #{number} ({q.get('question_type', 'esai').upper()} - {q.get('bloom_level', '')})\n",
        f"**Pertanyaan:** {q.get('question', '')}\n\n",
        f"**Jawaban Ideal:** {q.get('answer', '')}\n\n",
    ]
    if q.get("explanation"):
        parts.append(f"**Penjelasan & Konteks:** {q['explanation']}\n\n")
    if q.get("source_reference"):
        parts.append(f"**Referensi Materi:** `{q['source_reference']}`\n\n")
    parts.append("---\n\n")
    return "".join(parts)


def format_generation_summary(questions: list[dict[str, Any]], start_number: int = 1) -> str:
    """Markdown chat message listing the generated questions, numbered as in the whole session."""
    num_final = sum(1 for q in questions if q.get("status") == "final")
    num_review = sum(1 for q in questions if q.get("status") == "needs_review")

    parts = [
        f"Berhasil membuat {len(questions)} soal!\n\n",
        f"• **Lolos Validasi:** {num_final} | **Perlu Tinjauan:** {num_review}\n\n",
    ]
    parts += [_format_question(number, q) for number, q in enumerate(questions, start_number)]
    return "".join(parts)


def format_revision_summary(number: int, action: str, q: dict[str, Any]) -> str:
    """Markdown chat message showing the new version of Soal #number."""
    verb = "dibuat ulang" if action == "regenerate" else "direvisi"
    status = "lolos validasi" if q.get("status") == "final" else "perlu tinjauan"
    return f"Soal #{number} berhasil {verb} ({status}).\n\n" + _format_question(number, q)
