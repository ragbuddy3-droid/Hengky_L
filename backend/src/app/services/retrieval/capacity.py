"""Stage 0: estimate how many questions a chunk can support, without an LLM call.

Retrieval walks the ranked candidates and keeps adding chunks only until their summed capacity covers
the number of question candidates, so thin chunks (transitions, lists, exercises) are skipped and dense
chunks serve several questions. Stage 1 later replaces the estimate with the real number of testable points.
"""

import math
import re
from typing import Any

from app.core.config import get_settings
from app.services.retrieval.hybrid_search import is_exercise_or_instruction_chunk

MIN_CHUNK_CHARS = 200
_MIN_SENTENCE_WORDS = 6

# Words that mark a sentence stating a fact, definition, function, cause, process, or example
_INFORMATIVE_MARKERS = re.compile(
    r"\b(?:adalah|merupakan|disebut|yaitu|yakni|berfungsi|fungsi|terdiri|karena|sehingga|akibat|"
    r"menyebabkan|disebabkan|proses|tahap|tahapan|contoh|misalnya|antara lain|berupa|meliputi|"
    r"digunakan|menghasilkan|bertujuan|terjadi)\b",
    re.IGNORECASE,
)
_ENUMERATION = re.compile(r"^\s*(?:\d+|[a-e])[.)]\s+\S", re.IGNORECASE)

# Project / activity instructions ("Tahap 1: ...", "Siapkan ...", "Buatlah ...") describe what students
# should do in class, not book content; questions from them ask about the task instead of the material.
_INSTRUCTION_START = re.compile(
    r"^\s*(?:(?:\d+|[a-e])[.)]\s*)?(?:buatlah|siapkan|tentukan|tuliskan|carilah|cari|usahakan|kumpulkan|lakukan|"
    r"diskusikan|presentasikan|gambarlah|amati|amatilah|perhatikan|tempelkan|tempel|guntinglah|lipatlah|"
    r"ceritakan|sampaikan|bacalah|isilah|lengkapilah|ajak|mintalah|catatlah|susunlah|rancanglah)\b",
    re.IGNORECASE,
)
_PROJECT_MARKERS = re.compile(
    r"\b(?:proyek belajar|tujuan proyek|jurnal proyek|refleksi proyek|proyek ini|proyek kalian|"
    r"langkah pengerjaan|tahap \d+\s*:|kegiatan kelompok|lembar kerja|kreativitas kalian)",
    re.IGNORECASE,
)

# Chunk categories that carry book content (activity/discussion chunks produce "what did you do in class" questions)
PREFERRED_CATEGORIES = {"materi_pokok", "uraian_materi", "studi_kasus"}


def informative_sentence_count(text: str) -> int:
    """Enumerated items and fact-bearing sentences; instructions to the student do not count."""
    count = 0
    for line in text.splitlines():
        if _ENUMERATION.match(line) and len(line.split()) >= 3 and not _INSTRUCTION_START.match(line):
            count += 1
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if (
            len(sentence.split()) >= _MIN_SENTENCE_WORDS
            and _INFORMATIVE_MARKERS.search(sentence)
            and not _INSTRUCTION_START.match(sentence)
        ):
            count += 1
    return count


def instruction_count(text: str) -> int:
    """Instruction lines/sentences plus project-activity markers (a marker weighs as two instructions)."""
    units = [u for line in text.splitlines() for u in re.split(r"(?<=[.!?])\s+", line) if u.strip()]
    return sum(1 for u in units if _INSTRUCTION_START.match(u)) + 2 * len(_PROJECT_MARKERS.findall(text))


def is_project_or_instruction_chunk(text: str) -> bool:
    """Mostly project steps / activity instructions rather than explanatory material."""
    instructions = instruction_count(text)
    return instructions >= 3 and instructions > informative_sentence_count(text)


def estimate_capacity(chunk: dict[str, Any]) -> int:
    """0..max_questions_per_chunk: roughly one question per two informative sentences."""
    text = chunk.get("text", "")
    if len(text) < MIN_CHUNK_CHARS or is_exercise_or_instruction_chunk(text) or is_project_or_instruction_chunk(text):
        return 0
    capacity = math.ceil(informative_sentence_count(text) / 2)
    if (chunk.get("metadata") or {}).get("category") not in PREFERRED_CATEGORIES:
        capacity -= 1
    return max(0, min(get_settings().MAX_QUESTIONS_PER_CHUNK, capacity))


def relevance_score(chunk: dict[str, Any]) -> float | None:
    score = chunk.get("rrf_score")
    return float(score) if score is not None else None


def drop_weak_matches(ranked: list[dict[str, Any]], min_relative: float) -> list[dict[str, Any]]:
    """Remove candidates whose relevance is below `min_relative` x the best one (keeps the top hit)."""
    scores = [relevance_score(c) for c in ranked]
    if not ranked or scores[0] is None or not scores[0]:
        return ranked
    cutoff = scores[0] * min_relative
    return [c for c, s in zip(ranked, scores, strict=True) if s is None or s >= cutoff]


def select_by_capacity(
    ranked: list[dict[str, Any]],
    needed: int,
    max_chunks: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Take chunks in rank order until their estimated capacity covers `needed`; return (selected, rest).

    Chunks with capacity 0 are skipped (they stay out of `rest` too). If no chunk has any capacity,
    the best-ranked chunk is used anyway so the request is not left without material.
    """
    selected: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    total = 0
    for chunk in ranked:
        if total >= needed or len(selected) >= max_chunks:
            rest.append(chunk)
            continue
        capacity = estimate_capacity(chunk)
        if capacity == 0:
            continue
        selected.append({**chunk, "capacity": capacity})
        total += capacity
    if not selected and ranked:
        selected, rest = [{**ranked[0], "capacity": 1}], ranked[1:]
    return selected, rest
