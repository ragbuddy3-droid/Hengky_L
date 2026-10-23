"""Layer 1 non-LLM grounding check: cosine similarity against the blueprint's grounding evidence."""

from functools import cache
from typing import Any

import numpy as np

from app.services.retrieval.dense_index import DenseIndex
from app.services.validation.embedding_cache import EmbeddingCache


@cache
def _get_embedding_cache(model: Any) -> EmbeddingCache:
    """One embedding cache per embedder."""
    return EmbeddingCache(model, max_entries=500)


def compute_grounding_evidence_score(
    question_text: str,
    answer_text: str,
    grounding_evidence: str | None,
    fallback_chunks: list[str],
    dense_idx: DenseIndex
) -> dict[str, Any]:
    """
    Cosine similarity between (question + answer) and the blueprint's grounding evidence,
    falling back to the source chunks when the evidence is missing or too short.
    """
    qa_text = f"{question_text} Jawaban: {answer_text}".strip()
    cache = _get_embedding_cache(dense_idx.model)

    if grounding_evidence and len(grounding_evidence.strip()) >= 10:
        qa_emb, ev_emb = cache.encode_batch([qa_text, grounding_evidence.strip()])
        score = float(np.dot(qa_emb, ev_emb))
        return {"score": max(0.0, min(1.0, score)), "target": grounding_evidence[:100]}

    if fallback_chunks:
        qa_emb, *chunk_embs = cache.encode_batch([qa_text, *fallback_chunks])
        scores = sorted((float(np.dot(qa_emb, ch_emb)) for ch_emb in chunk_embs), reverse=True)
        top2_mean = float(np.mean(scores[:2]))
        fused_score = 0.8 * scores[0] + 0.2 * top2_mean
        return {"score": max(0.0, min(1.0, fused_score)), "target": "fallback_chunks"}

    return {"score": 0.0, "target": "none"}
