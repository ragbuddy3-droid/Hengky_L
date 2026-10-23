"""Hybrid retrieval combining dense vector search and sparse lexical search using Reciprocal Rank Fusion (RRF)."""

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.services.retrieval.dense_index import DenseIndex
from app.services.retrieval.sparse_index import SparseIndex


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
        return not (len(text_lower.split()) > 60 and ("adalah" in text_lower or "merupakan" in text_lower or "proses" in text_lower))

    # Detect numbered test items (e.g. 1. ... 2. ...) with question marks or imperatives
    sub_questions = re.findall(
        r'(?:^|\s)(?:\d+|[a-e])[\.\)]\s*(?:tuliskan|jelaskan|sebutkan|buatlah|isilah|apa|mengapa|bagaimana)',
        text_lower
    )
    return bool(len(sub_questions) >= 2 and text_lower.count('?') >= 1)


def reciprocal_rank_fusion(
    dense_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[dict[str, Any]]:
    """Weighted Reciprocal Rank Fusion: score = sum of weight / (k + rank) over the lists an item appears in."""
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    for results, weight in ((dense_results, dense_weight), (sparse_results, sparse_weight)):
        for rank, item in enumerate(results, 1):
            items.setdefault(item["id"], item)  # the dense hit wins when both lists have it
            scores[item["id"]] = scores.get(item["id"], 0.0) + weight / (k + rank)
    ranked = sorted(scores, key=lambda item_id: scores[item_id], reverse=True)
    return [{**items[item_id], "rrf_score": scores[item_id]} for item_id in ranked]


class HybridSearch:
    """Hybrid search orchestrator across Dense and Sparse indexes fused with weighted RRF."""

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
        chapters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run dense and sparse queries with doc-id/chapter filter, fuse with RRF and drop exercise-only chunks."""
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

        return (clean_results or fused)[:top_k]
