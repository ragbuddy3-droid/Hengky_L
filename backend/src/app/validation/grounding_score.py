"""Grounding validation (Layer 1)."""
import logging
import numpy as np

logger = logging.getLogger(__name__)

def compute_cosine_similarity(vec1, vec2) -> float:
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)

def compute_grounding_score(question_text: str, options: list[str] | dict | None, answer: str, source_chunks: list[str], embedding_model) -> float:
    """Embed question+answer and source chunks, compute combined max & top-2 similarity."""
    if not source_chunks:
        logger.warning("Grounding score: no source chunks provided, returning 0.0")
        return 0.0
    
    logger.info("Computing grounding score (source_chunks=%d)", len(source_chunks))
    
    opts_str = ""
    if options:
        if isinstance(options, dict):
            opts_str = " ".join([str(v) for v in options.values()])
        elif isinstance(options, list):
            opts_str = " ".join([str(v) for v in options])
            
    qa_text = f"{question_text} {opts_str} Jawaban: {answer}".strip()
    qa_embedding = embedding_model.encode([qa_text])[0]
    
    chunk_embeddings = embedding_model.encode(source_chunks)
    
    scores = [compute_cosine_similarity(qa_embedding, chunk_emb) for chunk_emb in chunk_embeddings]
    scores.sort(reverse=True)

    max_score = scores[0] if scores else 0.0
    top2_mean = np.mean(scores[:2]) if len(scores) >= 2 else max_score
    
    # Combined score: 80% max chunk similarity + 20% top-2 average similarity
    final_score = float(0.8 * max_score + 0.2 * top2_mean)
            
    logger.info("Grounding score computed: %.4f (max=%.4f, top2_mean=%.4f)",
                final_score, max_score, top2_mean)
    return final_score


def validate_grounding(score: float, threshold: float) -> bool:
    """Return True if score >= threshold."""
    passed = score >= threshold
    logger.info("Grounding validation: score=%.4f, threshold=%.4f -> %s",
                score, threshold, "PASS" if passed else "FAIL")
    return passed
