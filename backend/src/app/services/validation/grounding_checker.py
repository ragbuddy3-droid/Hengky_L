"""Layer 1 Non-LLM Grounding Checker calculating cosine similarity against blueprint grounding evidence."""

import logging
from typing import Any

import numpy as np

from app.services.retrieval.dense_index import DenseIndex
from app.services.validation.embedding_cache import EmbeddingCache

logger = logging.getLogger(__name__)

_emb_cache: EmbeddingCache | None = None


def _get_embedding_cache(model: Any) -> EmbeddingCache:
    """Get or create singleton embedding cache."""
    global _emb_cache
    if _emb_cache is None or _emb_cache._model is not model:
        _emb_cache = EmbeddingCache(model, max_entries=500)
    return _emb_cache


def compute_grounding_evidence_score(
    question_text: str,
    answer_text: str,
    grounding_evidence: str | None,
    fallback_chunks: list[str],
    dense_idx: DenseIndex
) -> dict[str, Any]:
    """
    Compute cosine similarity between (Question + Answer) and grounding_evidence.
    Per skema-prompting-rag-aqg.md:
    Layer 1 (Grounding Check) sebaiknya dihitung terhadap grounding_evidence spesifik dari blueprint,
    bukan terhadap seluruh isi chunk — supaya deteksi halusinasi lebih presisi.
    """
    qa_text = f"{question_text} Jawaban: {answer_text}".strip()
    model = dense_idx.model
    cache = _get_embedding_cache(model)

    if not qa_text:
        return {
            "score": 0.0,
            "target": "none",
            "is_evidence_based": False,
        }

    qa_emb = cache.encode(qa_text)

    # Priority 1: Compute against grounding_evidence if present
    if grounding_evidence and len(grounding_evidence.strip()) >= 10:
        ev_emb = cache.encode(grounding_evidence.strip())
        score = float(np.dot(qa_emb, ev_emb))
        return {
            "score": max(0.0, min(1.0, score)),
            "target": grounding_evidence[:100],
            "is_evidence_based": True,
        }

    # Priority 2: Fallback to source chunks if grounding_evidence is missing
    if fallback_chunks:
        chunk_embs = cache.encode_batch(fallback_chunks)
        scores = [float(np.dot(qa_emb, ch_emb)) for ch_emb in chunk_embs]
        scores.sort(reverse=True)
        max_score = scores[0] if scores else 0.0
        top2_mean = float(np.mean(scores[:2])) if len(scores) >= 2 else max_score
        fused_score = float(0.8 * max_score + 0.2 * top2_mean)
        return {
            "score": max(0.0, min(1.0, fused_score)),
            "target": "fallback_chunks",
            "is_evidence_based": False,
        }

    return {
        "score": 0.0,
        "target": "none",
        "is_evidence_based": False,
    }
