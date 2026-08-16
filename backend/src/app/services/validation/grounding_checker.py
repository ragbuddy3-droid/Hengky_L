"""Layer 1 Non-LLM Grounding Checker calculating cosine similarity against blueprint grounding evidence."""

import logging
from typing import Any

import numpy as np

from app.services.retrieval.dense_index import DenseIndex

logger = logging.getLogger(__name__)


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

    if not qa_text:
        return {
            "score": 0.0,
            "target": "none",
            "is_evidence_based": False,
        }

    qa_emb = model.encode([qa_text], normalize_embeddings=True)[0]

    # Priority 1: Compute against grounding_evidence if present
    if grounding_evidence and len(grounding_evidence.strip()) >= 10:
        ev_emb = model.encode([grounding_evidence.strip()], normalize_embeddings=True)[0]
        score = float(np.dot(qa_emb, ev_emb))
        return {
            "score": max(0.0, min(1.0, score)),
            "target": grounding_evidence[:100],
            "is_evidence_based": True,
        }

    # Priority 2: Fallback to source chunks if grounding_evidence is missing
    if fallback_chunks:
        chunk_embs = model.encode(fallback_chunks, normalize_embeddings=True)
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
