"""Request-level retrieval: load a document's chunks and pick only as many as the question candidates need.

Topic requests go through hybrid search (dense + BM25, RRF) with a relative relevance cutoff; topic-less
requests ("Buatkan 10 soal") sample chunks spread over different sections. Chunks are then taken in rank
order until their estimated capacity (Stage 0) covers the candidates; the rest of the ranked pool is kept
as reserve for capacity expansion after Stage 1 and for the top-up round.
"""

import hashlib
import logging
import random
import re
from collections import defaultdict
from typing import Any, NamedTuple

from app.core.config import get_settings
from app.core.database import get_session
from app.models.db_models import Chunk
from app.services.retrieval.capacity import MIN_CHUNK_CHARS, drop_weak_matches, select_by_capacity
from app.services.retrieval.dense_index import DenseIndex
from app.services.retrieval.hybrid_search import HybridSearch, is_exercise_or_instruction_chunk
from app.services.retrieval.sparse_index import SparseIndex

logger = logging.getLogger(__name__)

# Chunk categories that carry book content (activity/discussion chunks produce "what did you do in class" questions)
PREFERRED_CHUNK_CATEGORIES = {"materi_pokok", "uraian_materi", "studi_kasus"}

_ROMAN_TO_INT = {
    "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
    "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10",
}

# Generation meta-words that carry no topic ("buatkan 5 soal C2 bab 3 tentang ...")
_META_PATTERNS = [
    r'\b\d+\s*(?:soal|pertanyaan)\b',
    r'\bbuatkan\b', r'\bbuat\b', r'\bbikin\b', r'\bgenerate\b', r'\bberikan\b', r'\bminta\b', r'\btolong\b',
    r'\bsoal\b', r'\bpertanyaan\b', r'\blatihan\b', r'\btugas\b', r'\bujicoba\b',
    r'\bc[1-6]\b', r'\besai\b', r'\bisian\s*singkat\b', r'\bisian\b', r'\bpilihan\s*ganda\b',
    r'\bdong\b', r'\bya\b', r'\bsebanyak\b', r'\bjumlah\b',
    # Chapter is handled separately; filler words carry no topic
    r'\bbab\s*[\w]+', r'\btentang\b', r'\bmengenai\b', r'\bmateri\b', r'\blevel\b', r'\btingkat\b',
    r'\bberagam\b', r'\bcampur\b', r'\bdari\b', r'\buntuk\b', r'\bdengan\b',
]


class RetrievalResult(NamedTuple):
    chunks: list[dict[str, Any]]  # selected by capacity, each carrying its estimated "capacity"
    reserve: list[dict[str, Any]]  # rest of the ranked pool, analysed only when more points are needed


# ── Shared indexes ──

_dense_index: DenseIndex | None = None
_sparse_cache: dict[str, SparseIndex] = {}


def get_shared_dense_index() -> DenseIndex:
    """Get or create the singleton DenseIndex (loads the embedding model once)."""
    global _dense_index
    if _dense_index is None:
        settings = get_settings()
        _dense_index = DenseIndex(
            persist_dir=settings.CHROMA_PERSIST_DIR,
            collection_name="rag_aqg_chunks",
            embedding_model_name=settings.EMBEDDING_MODEL,
        )
    return _dense_index


def _get_sparse_index(document_id: str, chunks: list[dict[str, Any]]) -> SparseIndex:
    """BM25 index over exactly these chunks, cached per document + chunk set."""
    content_hash = hashlib.md5("".join(c["id"] for c in chunks).encode()).hexdigest()[:12]
    key = f"{document_id}_{len(chunks)}_{content_hash}"
    if key not in _sparse_cache:
        sparse = SparseIndex()
        sparse.build_index(chunks)
        _sparse_cache[key] = sparse
    return _sparse_cache[key]


def invalidate_sparse_cache(document_id: str) -> None:
    """Drop cached BM25 indexes of a deleted document."""
    for key in [k for k in _sparse_cache if k.startswith(f"{document_id}_")]:
        del _sparse_cache[key]


# ── Query & chunk helpers ──

def extract_chapter_number(chapter_str: str | None) -> str | None:
    """Normalize 'Bab 3', 'BAB III', '3' to '3'."""
    if not chapter_str:
        return None
    match = re.search(
        r'\b(?:Bab|Chapter|Unit|Pembelajaran|Modul)?\s*([\d]+|[IVXLCDM]+)\b',
        str(chapter_str),
        re.IGNORECASE,
    )
    if not match:
        return None
    val = match.group(1).upper()
    return _ROMAN_TO_INT.get(val, val)


def sanitize_retrieval_query(user_prompt: str) -> str:
    """Strip generation meta-words from the prompt, leaving only topical keywords ('' if there is no topic)."""
    if not user_prompt:
        return ""
    text = user_prompt.lower()
    for pattern in _META_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^\w\s-]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def load_document_chunks(document_id: str) -> list[dict[str, Any]]:
    """All chunks of a document in the dict shape used by retrieval and generation."""
    with get_session() as db:
        rows = db.query(Chunk).filter(Chunk.document_id == document_id).all()
        return [
            {
                "id": c.id,
                "text": c.text,
                "metadata": {
                    "document_id": c.document_id,
                    "category": c.category,
                    "chapter": c.chapter or "",
                    "section_heading": c.section_heading or "",
                    "page_number": c.page_number or 1,
                    "chunk_index": c.chunk_index or 0,
                    "section_type": c.section_type or "materi_pokok",
                },
            }
            for c in rows
        ]


def filter_by_chapter(chunks: list[dict[str, Any]], chapter: str | None) -> list[dict[str, Any]]:
    """Keep only chunks of the requested chapter; unchanged if the chapter is unknown in this document."""
    target = extract_chapter_number(chapter)
    if not target:
        return chunks
    matched = [c for c in chunks if extract_chapter_number(c["metadata"].get("chapter", "")) == target]
    return matched or chunks


def _is_usable(chunk: dict[str, Any]) -> bool:
    text = chunk.get("text", "")
    return len(text) >= MIN_CHUNK_CHARS and not is_exercise_or_instruction_chunk(text)


def _is_preferred(chunk: dict[str, Any]) -> bool:
    return (chunk.get("metadata") or {}).get("category") in PREFERRED_CHUNK_CATEGORIES


def select_diverse_chunks(
    chunks: list[dict[str, Any]],
    k: int,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Pick up to k content chunks, one per section first (in pick order, so a prefix is still diverse)."""
    rng = rng or random.Random()
    usable = [c for c in chunks if _is_usable(c)] or chunks
    preferred = [c for c in usable if _is_preferred(c)]
    pool = preferred if len(preferred) >= k else usable

    by_section: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in pool:
        meta = c["metadata"]
        by_section[(meta.get("chapter", ""), meta.get("section_heading", ""))].append(c)

    sections = list(by_section.values())
    rng.shuffle(sections)
    picked = [rng.choice(group) for group in sections[:k]]
    if len(picked) < k:
        picked_ids = {c["id"] for c in picked}
        rest = [c for c in pool if c["id"] not in picked_ids]
        picked += rng.sample(rest, min(k - len(picked), len(rest)))
    return picked


def _hybrid_rank(
    query: str,
    document_id: str,
    chunks: list[dict[str, Any]],
    chapters: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Hybrid search restricted to `chunks` (and to `chapters` on the dense side), content chunks first."""
    settings = get_settings()
    hybrid = HybridSearch(
        dense_index=get_shared_dense_index(),
        sparse_index=_get_sparse_index(document_id, chunks),
        dense_weight=settings.HYBRID_DENSE_WEIGHT,
        sparse_weight=settings.HYBRID_SPARSE_WEIGHT,
    )
    candidates = hybrid.search(
        query=query,
        top_k=limit * 2,
        document_id=document_id,
        candidate_k=settings.CANDIDATE_TOP_K,
        enable_rerank=settings.RERANKER_ENABLED,
        chapters=chapters,
    )
    allowed = {c["id"] for c in chunks}
    candidates = [c for c in candidates if c["id"] in allowed]
    # Stable partition keeps relevance order inside each group
    return [c for c in candidates if _is_preferred(c)] + [c for c in candidates if not _is_preferred(c)]


def retrieve_chunks(
    document_id: str,
    chunks: list[dict[str, Any]],
    user_prompt: str,
    chapter: str | None,
    needed: int,
) -> RetrievalResult:
    """Choose the fewest relevant chunks whose estimated capacity covers `needed` question candidates."""
    settings = get_settings()
    pool_size = settings.MAX_CONTEXT_CHUNKS + settings.RESERVE_CHUNKS

    scoped = filter_by_chapter(chunks, chapter) if chapter else chunks
    chapters = sorted({c["metadata"]["chapter"] for c in scoped}) if scoped is not chunks else None
    topic_query = sanitize_retrieval_query(user_prompt)

    if not topic_query:
        # "Buatkan 10 soal" has no topic: searching with the raw prompt returns arbitrary chunks,
        # so spread the questions over different sections of the document/chapter instead.
        ranked = select_diverse_chunks(scoped, pool_size)
    else:
        query = f"{topic_query} {chapters[0]}" if chapters else topic_query
        ranked = drop_weak_matches(
            _hybrid_rank(query, document_id, scoped, chapters, pool_size), settings.MIN_RELATIVE_SCORE,
        )
        logger.info("[Retrieval] query='%s' -> %d relevant candidates.", query, len(ranked))

    selected, reserve = select_by_capacity(ranked[:pool_size] or scoped[:pool_size], needed, settings.MAX_CONTEXT_CHUNKS)
    if not topic_query:
        selected.sort(key=lambda c: c["metadata"].get("chunk_index", 0))
    logger.info(
        "[Retrieval] %d chunks selected for %d candidates (est. capacity %d), %d in reserve.",
        len(selected), needed, sum(c["capacity"] for c in selected), len(reserve),
    )
    return RetrievalResult(chunks=selected, reserve=reserve)
