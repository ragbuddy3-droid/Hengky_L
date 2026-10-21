"""Hybrid retrieval combining dense vector search and sparse lexical search using Reciprocal Rank Fusion (RRF)."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.services.retrieval.dense_index import DenseIndex
from app.services.retrieval.sparse_index import SparseIndex

logger = logging.getLogger(__name__)


def is_exercise_or_instruction_chunk(chunk_text: str) -> bool:
    """
    Detect if chunk is PURELY a textbook exercise list / rubric table / reflection box / assignment prompt.
    Preserves chunks that contain conceptual definitions or explanatory narratives.
    """
    if not chunk_text:
        return False
    text_lower = chunk_text.lower()

    # 1. Rubric / scoring tables
    rubric_phrases = [
        "tabel penilaian",
        "skor maksimal",
        "kriteria skor",
        "paraf guru",
        "aspek yang dinilai",
        "nama kriteria skor",
        "berikut tabel penilaian",
    ]
    if any(phrase in text_lower for phrase in rubric_phrases):
        return True

    # 2. End-of-chapter reflection boxes
    reflection_phrases = [
        "selamat! kalian sudah menyelesaikan bab",
        "pengalaman belajar favorit saya",
        "apa saja yang sudah kalian pelajari di bab",
        "apa yang sudah kamu pelajari mengenai",
        "tambahkan 2 pengalaman belajar lain",
        "ayo, merenungkan",
        "berilah tanda centang",
        "beri tanda centang",
        "renungan bab",
        "salin refleksi",
        "salin tabel berikut di buku tugas",
    ]
    if any(phrase in text_lower for phrase in reflection_phrases):
        return True

    # 3. Pure exercise prompts
    pure_exercise_phrases = [
        "jawablah pertanyaan",
        "pilihlah jawaban",
        "isilah titik-titik",
        "lembar kerja",
        "uji kompetensi",
        "tugas kelompok",
        "tugas individu",
        "diskusikan bersama",
        "latihan soal",
    ]

    if any(phrase in text_lower for phrase in pure_exercise_phrases):
        # Allow long explanatory concept paragraphs (> 60 words) that merely mention discussion
        if len(text_lower.split()) > 60 and ("adalah" in text_lower or "merupakan" in text_lower or "proses" in text_lower):
            return False
        return True

    # Detect numbered test items (e.g. 1. ... 2. ...) with question marks or imperatives
    sub_questions = re.findall(
        r'(?:^|\s)(?:\d+|[a-e])[\.\)]\s*(?:tuliskan|jelaskan|sebutkan|buatlah|isilah|apa|mengapa|bagaimana)',
        text_lower
    )
    if len(sub_questions) >= 2 and text_lower.count('?') >= 1:
        return True

    return False


def reciprocal_rank_fusion(
    dense_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[dict[str, Any]]:
    """Implement weighted Reciprocal Rank Fusion algorithm across ranked lists."""
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for rank, item in enumerate(dense_results):
        item_id = item["id"]
        if item_id not in scores:
            scores[item_id] = 0.0
            items[item_id] = item
        scores[item_id] += dense_weight * (1.0 / (k + rank + 1))

    for rank, item in enumerate(sparse_results):
        item_id = item["id"]
        if item_id not in scores:
            scores[item_id] = 0.0
            items[item_id] = item
        scores[item_id] += sparse_weight * (1.0 / (k + rank + 1))

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results: list[dict[str, Any]] = []
    for item_id, score in sorted_items:
        res = items[item_id].copy()
        res["rrf_score"] = score
        results.append(res)

    return results


class HybridSearch:
    """Hybrid search orchestrator across Dense and Sparse indexes with Cross-Score Reranking."""

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

    def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: str | None = None,
        candidate_k: int = 15,
        enable_rerank: bool = True,
        chapters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run dense and sparse queries with doc-id/chapter filter, fuse with RRF, and re-rank with semantic cross-scoring."""
        fetch_k = max(top_k * 3, candidate_k)

        with ThreadPoolExecutor(max_workers=2) as executor:
            dense_future = executor.submit(self.dense_index.query, query, fetch_k, document_id, chapters)
            sparse_future = executor.submit(self.sparse_index.query, query, fetch_k)
            dense_results = dense_future.result()
            sparse_results = sparse_future.result()

        fused = reciprocal_rank_fusion(
            dense_results,
            sparse_results,
            dense_weight=self.dense_weight,
            sparse_weight=self.sparse_weight
        )

        # Filter out pure test sheet chunks
        clean_results = [
            chunk for chunk in fused
            if not is_exercise_or_instruction_chunk(chunk.get("text", ""))
        ]

        if not clean_results:
            clean_results = fused

        if not clean_results:
            return []

        # Re-scoring stage: Re-calculate precise semantic cosine similarity between query and candidate texts
        if enable_rerank and len(clean_results) > 1:
            try:
                candidate_pool = clean_results[:candidate_k]
                query_emb = self.dense_index.model.encode([query], normalize_embeddings=True)[0]
                chunk_texts = [c.get("text", "") for c in candidate_pool]
                chunk_embs = self.dense_index.model.encode(chunk_texts, normalize_embeddings=True)

                scored_candidates = []
                for idx, c in enumerate(candidate_pool):
                    sem_sim = float(sum(query_emb * chunk_embs[idx]))
                    # Combined final score: 70% direct semantic similarity + 30% RRF rank score
                    rrf_norm = float(c.get("rrf_score", 0.0)) * 50.0  # normalize RRF to ~0-1
                    combined_score = 0.70 * sem_sim + 0.30 * rrf_norm

                    c_copy = c.copy()
                    c_copy["semantic_score"] = sem_sim
                    c_copy["final_score"] = combined_score
                    scored_candidates.append(c_copy)

                scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)
                return scored_candidates[:top_k]
            except Exception as e:
                logger.warning("Reranking failed (%s), falling back to RRF results", e)

        return clean_results[:top_k]
