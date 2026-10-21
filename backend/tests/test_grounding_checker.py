"""Tests for Layer 1 Non-LLM Grounding Checker and EmbeddingCache."""

from unittest.mock import MagicMock

import numpy as np

from app.services.validation.embedding_cache import EmbeddingCache
from app.services.validation.grounding_checker import compute_grounding_evidence_score


def test_embedding_cache_reduces_encode_calls():
    """EmbeddingCache should only call model.encode once for the same text."""
    mock_model = MagicMock()
    # Mock return shape
    dummy_vec = np.array([0.5, 0.5, 0.5, 0.5])
    dummy_vec = dummy_vec / np.linalg.norm(dummy_vec)
    mock_model.encode.return_value = np.array([dummy_vec])

    cache = EmbeddingCache(mock_model, max_entries=10)

    # First call
    vec1 = cache.encode("Fotosintesis pada tumbuhan")
    # Second call (same text)
    vec2 = cache.encode("Fotosintesis pada tumbuhan")

    assert np.allclose(vec1, vec2)
    assert mock_model.encode.call_count == 1


def test_embedding_cache_batch_encoding():
    """EmbeddingCache should encode multiple texts and reuse cached items."""
    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, **kwargs: np.array([
        np.array([1.0, 0.0]) for _ in texts
    ])

    cache = EmbeddingCache(mock_model, max_entries=10)
    cache.encode("Text A")

    # Now batch encode Text A and Text B
    results = cache.encode_batch(["Text A", "Text B"])
    assert len(results) == 2
    # encode was called once for Text A initially, and once for [Text B] in batch
    assert mock_model.encode.call_count == 2


def test_grounding_score_empty_input():
    """Empty question/answer text should return 0.0 grounding score."""
    mock_dense = MagicMock()
    mock_dense.model = MagicMock()

    res = compute_grounding_evidence_score(
        question_text="",
        answer_text="",
        grounding_evidence=None,
        fallback_chunks=[],
        dense_idx=mock_dense,
    )
    assert res["score"] == 0.0
    assert res["target"] == "none"


def test_grounding_score_with_evidence():
    """Matching question+answer and evidence should produce high cosine similarity."""
    mock_dense = MagicMock()
    mock_model = MagicMock()

    # Unit vector representing perfect alignment
    aligned_vec = np.array([1.0, 0.0, 0.0])
    mock_model.encode.side_effect = lambda texts, **kwargs: np.array([aligned_vec for _ in texts])
    mock_dense.model = mock_model

    res = compute_grounding_evidence_score(
        question_text="Apa fungsi daun?",
        answer_text="Daun berfungsi sebagai tempat fotosintesis.",
        grounding_evidence="Daun berfungsi sebagai tempat berlangsungnya proses fotosintesis pada tumbuhan.",
        fallback_chunks=[],
        dense_idx=mock_dense,
    )
    assert res["score"] > 0.8
    assert mock_model.encode.call_count == 1
