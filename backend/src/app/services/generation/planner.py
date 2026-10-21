"""Question planning: Bloom level mix, validated knowledge points per chunk, capacity-based allocation, focus context."""

from typing import Any

from app.core.database import get_session
from app.models.db_models import ChatSession, Question
from app.services.generation.schemas import ContentAnalysis
from app.services.validation.quality_checks import (
    find_book_navigation_issue,
    find_clarity_issue,
    is_reflective_question,
    jaccard,
    tokens,
)

# Used round-robin when the user does not ask for a specific level
MIXED_BLOOM_LEVELS = ["C1-Mengingat", "C2-Memahami", "C3-Mengaplikasikan", "C4-Menganalisis"]

NO_FEW_SHOT = "Tidak ada contoh tambahan."

# Knowledge points this similar (token Jaccard) count as the same point
_POINT_DUPLICATE_THRESHOLD = 0.6

# Share of a Stage 1 source quote's words that must occur in the chunk for the point to count as grounded
_QUOTE_COVERAGE = 0.6


# ── Bloom levels ──

def normalize_bloom_level(level: str | None) -> str | None:
    """Map a requested level to the SD range C1-C4; None means 'mixed levels'."""
    if not level:
        return None
    for full in MIXED_BLOOM_LEVELS:
        if full[:2] in level.upper():
            return full
    return "C2-Memahami"  # C5/C6 are out of scope for SD


def assign_bloom_levels(count: int, requested: str | None, offset: int = 0) -> list[str]:
    """Fixed level when requested, otherwise round-robin C1-C4 (10 -> 3/3/2/2) starting at `offset`."""
    fixed = normalize_bloom_level(requested)
    if fixed:
        return [fixed] * count
    return [MIXED_BLOOM_LEVELS[(offset + i) % len(MIXED_BLOOM_LEVELS)] for i in range(count)]


def bloom_order(q: dict[str, Any]) -> int:
    level = q.get("bloom_level", "")
    return next((i for i, lvl in enumerate(MIXED_BLOOM_LEVELS) if lvl[:2] in level), len(MIXED_BLOOM_LEVELS))


def candidate_count(num_questions: int) -> int:
    """Generate a little more than requested so validation failures do not leave the batch short."""
    return num_questions + (1 if num_questions <= 3 else 2)


# ── Knowledge points per chunk ──

def _quote_in_chunk(quote: str, chunk_tokens: set[str]) -> bool:
    """The quote must come from the chunk: most of its words appear in the chunk text."""
    quote_tokens = tokens(quote)
    if not quote_tokens:
        return False
    return len(quote_tokens & chunk_tokens) / len(quote_tokens) >= _QUOTE_COVERAGE


def valid_points(chunk: dict[str, Any], analysis: ContentAnalysis) -> list[dict[str, Any]]:
    """Stage 1 points of a chunk whose source quote is really in the chunk, without near-duplicates.

    The number of valid points is the chunk's real question capacity.
    """
    chunk_tokens = tokens(chunk.get("text", ""))
    candidates = [(tc.point, tc.source_quote) for tc in analysis.testable_content if tc.point]
    if not candidates:
        candidates = [(fact, fact) for fact in analysis.key_facts]

    points: list[dict[str, Any]] = []
    seen: list[set[str]] = []
    for point, quote in candidates:
        toks = tokens(point)
        if not _quote_in_chunk(quote, chunk_tokens) or any(jaccard(toks, s) >= _POINT_DUPLICATE_THRESHOLD for s in seen):
            continue
        points.append({"point": point, "quote": quote, "chunk_id": chunk["id"]})
        seen.append(toks)
    return points


def chunk_point_lists(
    chunks: list[dict[str, Any]],
    analyses: dict[str, ContentAnalysis],
    exclude_points: list[str] | None = None,
) -> list[list[dict[str, Any]]]:
    """Valid points per chunk (in chunk rank order), dropping points similar to one of an earlier chunk or `exclude_points`."""
    seen = [tokens(p) for p in (exclude_points or [])]
    lists: list[list[dict[str, Any]]] = []
    for chk in chunks:
        if chk["id"] not in analyses:
            continue
        kept = []
        for spec in valid_points(chk, analyses[chk["id"]]):
            toks = tokens(spec["point"])
            if not any(jaccard(toks, s) >= _POINT_DUPLICATE_THRESHOLD for s in seen):
                kept.append(spec)
                seen.append(toks)
        lists.append(kept)
    return lists


def interleave(point_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Rank-wise merge (A1, B1, ..., A2, B2, ...) so a prefix spreads over the chunks."""
    longest = max((len(p) for p in point_lists), default=0)
    return [points[rank] for rank in range(longest) for points in point_lists if rank < len(points)]


def real_capacity(point_lists: list[list[dict[str, Any]]], max_per_chunk: int) -> int:
    return sum(min(len(points), max_per_chunk) for points in point_lists)


def allocate_items(
    point_lists: list[list[dict[str, Any]]],
    levels: list[str],
    max_per_chunk: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Give each chunk up to `max_per_chunk` questions, round-robin in rank order; return (items, spare points).

    A chunk's questions get different Bloom levels where the mix allows. When there are fewer points than
    levels, spare points and then already used points are reused with the remaining levels.
    """
    chosen: list[dict[str, Any]] = []
    for rank in range(max_per_chunk):
        for points in point_lists:
            if rank < len(points) and len(chosen) < len(levels):
                chosen.append(points[rank])
    chosen_ids = {id(p) for p in chosen}
    spare = [p for p in interleave(point_lists) if id(p) not in chosen_ids]

    if chosen and len(chosen) < len(levels):
        # Points beyond a chunk's cap first, then points already chosen (with another level / angle)
        pool = spare + chosen
        need = len(levels) - len(chosen)
        chosen += [pool[i % len(pool)] for i in range(need)]
        spare = spare[need:]

    remaining = list(levels[:len(chosen)])
    used_by_chunk: dict[str, set[str]] = {}
    items = []
    for spec in chosen:
        used = used_by_chunk.setdefault(spec["chunk_id"], set())
        level = next((lvl for lvl in remaining if lvl not in used), remaining[0])
        remaining.remove(level)
        used.add(level)
        items.append({**spec, "bloom_level": level})
    return items, spare


def planning_summary(analyses: list[ContentAnalysis]) -> ContentAnalysis:
    """Topic and key concepts of the selected chunks: all Stage 2 needs to plan the cognitive operation per level."""
    summary = ContentAnalysis(topic=next((a.topic for a in analyses if a.topic), "Materi Pembelajaran"))
    for a in analyses:
        summary.key_concepts += a.key_concepts[:3]
    return summary


# ── Per-item context ──

def source_reference(chunk: dict[str, Any]) -> str:
    meta = chunk.get("metadata", {})
    chap = meta.get("chapter", "")
    sec = meta.get("section_heading", "")
    page_num = meta.get("page_number")
    page_str = f" (Hal. {page_num})" if page_num else ""
    if chap and sec:
        return f"{chap} - {sec}{page_str}"
    if chap or sec:
        return f"{chap or sec}{page_str}"
    return f"Materi Buku{page_str}"


def focus_context(chunk: dict[str, Any]) -> str:
    """The material a question is generated, judged, and refined against: its own chunk only.

    Fixed chunks overlap by 150 characters, so sentences at a chunk border are still complete.
    """
    return chunk.get("text", "")


def load_few_shots(document_id: str, levels: list[str]) -> dict[str, str]:
    """Per level: two recent validated, clearly worded questions from this document."""
    return {lvl: _load_few_shot(document_id, lvl) for lvl in dict.fromkeys(levels)}


def _load_few_shot(document_id: str, bloom_level: str) -> str:
    with get_session() as db:
        past_qs = (
            db.query(Question)
            .join(ChatSession, Question.session_id == ChatSession.id)
            .filter(
                ChatSession.document_id == document_id,
                Question.status == "final",
                Question.bloom_level == bloom_level,
                Question.quality_warnings.is_(None),
            )
            .order_by(Question.created_at.desc())
            .limit(10)
            .all()
        )
        good = [
            q for q in past_qs
            if not find_clarity_issue(str(q.question_text))
            and not is_reflective_question(str(q.question_text))
            and not find_book_navigation_issue(str(q.question_text))
        ][:2]
        if not good:
            return NO_FEW_SHOT
        return "\n".join(
            f"Contoh {i}:\n  Pertanyaan: {q.question_text}\n  Jawaban: {q.answer_key}"
            for i, q in enumerate(good, 1)
        )
