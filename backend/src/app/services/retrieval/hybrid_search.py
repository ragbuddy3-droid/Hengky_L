"""Hybrid retrieval combining dense vector search and sparse lexical search using Reciprocal Rank Fusion (RRF)."""

import logging
import re
from typing import Any

from app.services.retrieval.dense_index import DenseIndex
from app.services.retrieval.sparse_index import SparseIndex

logger = logging.getLogger(__name__)


def is_exercise_or_instruction_chunk(chunk_text: str) -> bool:
    """Detect if chunk contains textbook exercise questions, assignment prompts, or summary questions."""
    if not chunk_text:
        return False
    text_lower = chunk_text.lower()

    # Direct exercise/assignment phrase triggers
    exercise_phrases = [
        "menjawab pertanyaan", "pertanyaan berikut", "soal berikut",
        "rangkuman dengan menjawab", "buat rangkuman dengan",
        "tugas individu", "tugas kelompok", "latihan soal", "uji kompetensi",
        "jawablah pertanyaan", "pilihlah jawaban", "isilah titik-titik"
    ]
    if any(phrase in text_lower for phrase in exercise_phrases):
        return True

    # Detect multi-question sub-item patterns (e.g., "a. Tuliskan...", "b. Jelaskan...", "c. Buatkan...")
    sub_questions = re.findall(
        r'[a-e1-9][\.\)]\s*(tuliskan|jelaskan|sebutkan|buatlah|buatkan|isilah|urutkan|pasangkan|bagaimana|mengapa|apa)',
        text_lower
    )
    if len(sub_questions) >= 2 or ("menjawab pertanyaan" in text_lower and len(sub_questions) >= 1):
        return True

    # High frequency of question marks without explanatory concept definitions
    q_mark_count = text_lower.count('?')
    return bool(
        q_mark_count >= 2
        and not re.search(r'\b(adalah|merupakan|yaitu|disebut|fungsi|proses|sistem|organ)\b', text_lower)
    )




def reciprocal_rank_fusion(
    dense_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    k: int = 60
) -> list[dict[str, Any]]:
    """Implement Reciprocal Rank Fusion algorithm across ranked lists."""
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for rank, item in enumerate(dense_results):
        item_id = item["id"]
        if item_id not in scores:
            scores[item_id] = 0.0
            items[item_id] = item
        scores[item_id] += 1.0 / (k + rank + 1)

    for rank, item in enumerate(sparse_results):
        item_id = item["id"]
        if item_id not in scores:
            scores[item_id] = 0.0
            items[item_id] = item
        scores[item_id] += 1.0 / (k + rank + 1)

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results: list[dict[str, Any]] = []
    for item_id, score in sorted_items:
        res = items[item_id].copy()
        res["rrf_score"] = score
        results.append(res)

    return results


class HybridSearch:
    """Hybrid search orchestrator across Dense and Sparse indexes."""

    def __init__(
        self,
        dense_index: DenseIndex,
        sparse_index: SparseIndex,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4
    ):
        self.dense_index = dense_index
        self.sparse_index = sparse_index
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Run dense and sparse queries, fuse with RRF, and filter noise/exercises."""
        dense_results = self.dense_index.query(query, top_k=top_k * 2)
        sparse_results = self.sparse_index.query(query, top_k=top_k * 2)

        fused = reciprocal_rank_fusion(dense_results, sparse_results)

        # Filter out chunks that are pure textbook exercises / assignments
        clean_results = [
            chunk for chunk in fused
            if not is_exercise_or_instruction_chunk(chunk.get("text", ""))
        ]

        if not clean_results:
            logger.warning("Anti-exercise filter removed all chunks, falling back to raw fused results.")
            clean_results = fused

        return clean_results[:top_k]
