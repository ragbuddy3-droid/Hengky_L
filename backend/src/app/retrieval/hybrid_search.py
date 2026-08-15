"""Hybrid search with RRF."""
import logging

logger = logging.getLogger(__name__)

def reciprocal_rank_fusion(dense_results: list[dict], sparse_results: list[dict], k: int = 60) -> list[dict]:
    """Implement RRF algorithm."""
    logger.debug("RRF fusion: dense_results=%d, sparse_results=%d, k=%d",
                len(dense_results), len(sparse_results), k)
    
    scores = {}
    items = {}
    
    for rank, item in enumerate(dense_results):
        item_id = item['id']
        if item_id not in scores:
            scores[item_id] = 0
            items[item_id] = item
        scores[item_id] += 1.0 / (k + rank + 1)
        
    for rank, item in enumerate(sparse_results):
        item_id = item['id']
        if item_id not in scores:
            scores[item_id] = 0
            items[item_id] = item
        scores[item_id] += 1.0 / (k + rank + 1)
        
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    results = []
    for item_id, score in sorted_items:
        res = items[item_id].copy()
        res['rrf_score'] = score
        results.append(res)
    
    logger.debug("RRF fusion produced %d unique results", len(results))
    return results

class HybridSearch:
    def __init__(self, dense_index, sparse_index, dense_weight: float = 0.5, sparse_weight: float = 0.5):
        self.dense_index = dense_index
        self.sparse_index = sparse_index
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        logger.info("HybridSearch initialized (dense_weight=%.2f, sparse_weight=%.2f)",
                    dense_weight, sparse_weight)
        
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Run both indexes, fuse with RRF, return top-k."""
        truncated_query = query[:80] + "..." if len(query) > 80 else query
        logger.info("Hybrid search started (top_k=%d): '%s'", top_k, truncated_query)
        
        dense_results = self.dense_index.query(query, top_k=top_k * 2)
        sparse_results = self.sparse_index.query(query, top_k=top_k * 2)
        
        logger.info("  Dense returned %d results, Sparse returned %d results",
                    len(dense_results), len(sparse_results))
        
        fused = reciprocal_rank_fusion(dense_results, sparse_results)
        final = fused[:top_k]
        
        if final:
            top_rrf = final[0].get('rrf_score', 0.0)
            logger.info("Hybrid search complete: %d results returned (top_rrf_score=%.4f)",
                        len(final), top_rrf)
        else:
            logger.info("Hybrid search complete: 0 results returned")
        
        return final
