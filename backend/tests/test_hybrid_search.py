"""Tests for Hybrid Search, BM25 Sparse Index, and RRF Fusion."""

from app.services.retrieval.hybrid_search import (
    is_exercise_or_instruction_chunk,
    reciprocal_rank_fusion,
)
from app.services.retrieval.sparse_index import SparseIndex


def test_rrf_fusion_combines_rankings():
    """RRF should combine dense and sparse rankings correctly."""
    dense_results = [
        {"id": "doc_1", "text": "Fotosintesis pada daun", "score": 0.95},
        {"id": "doc_2", "text": "Respirasi pada akar", "score": 0.85},
    ]
    sparse_results = [
        {"id": "doc_2", "text": "Respirasi pada akar", "score": 4.2},
        {"id": "doc_3", "text": "Klorofil hijau", "score": 3.1},
    ]

    fused = reciprocal_rank_fusion(dense_results, sparse_results, k=60)
    assert len(fused) == 3
    # doc_2 appears in both, so its RRF score should be highest
    assert fused[0]["id"] == "doc_2"
    assert "rrf_score" in fused[0]


def test_exercise_filter_removes_exercise_chunks():
    """Anti-exercise filter should detect and flag exercise/assignment chunks."""
    exercise_chunk_1 = "Jawablah pertanyaan berikut dengan tepat: 1. Apa itu fotosintesis? 2. Jelaskan fungsinya!"
    exercise_chunk_2 = "Tugas Kelompok: Diskusikan bersama teman sebangkumu mengenai daur air."
    concept_chunk = "Fotosintesis adalah proses pembentukan makanan pada tumbuhan hijau dengan bantuan cahaya matahari."

    assert is_exercise_or_instruction_chunk(exercise_chunk_1) is True
    assert is_exercise_or_instruction_chunk(exercise_chunk_2) is True
    assert is_exercise_or_instruction_chunk(concept_chunk) is False


def test_sparse_index_build_and_query():
    """BM25 sparse index should correctly tokenize and score keyword matches."""
    chunks = [
        {"id": "c1", "text": "Organ pernapasan manusia terdiri atas hidung, tenggorokan, dan paru-paru."},
        {"id": "c2", "text": "Sistem peredaran darah manusia dipompa oleh organ jantung."},
        {"id": "c3", "text": "Tumbuhan memerlukan sinar matahari dan air untuk fotosintesis."},
    ]

    sparse = SparseIndex()
    sparse.build_index(chunks)

    results = sparse.query("paru-paru pernapasan", top_k=2)
    assert len(results) >= 1
    assert results[0]["id"] == "c1"


def test_sparse_index_empty_query():
    """Empty query should safely return empty results."""
    sparse = SparseIndex()
    sparse.build_index([{"id": "c1", "text": "Teks materi"}])

    assert sparse.query("") == []
    assert sparse.query("   ") == []
