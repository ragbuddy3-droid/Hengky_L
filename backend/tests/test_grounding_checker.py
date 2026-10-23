"""Tests for the Layer 1 non-LLM grounding checker."""

from unittest.mock import MagicMock

import numpy as np

from app.services.validation.grounding_checker import compute_grounding_evidence_score


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
