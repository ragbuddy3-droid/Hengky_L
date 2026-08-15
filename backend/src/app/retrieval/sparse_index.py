"""BM25 sparse retrieval."""
import time
import string
import logging
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

class SparseIndex:
    def __init__(self):
        self.bm25 = None
        self.corpus_data = []
        logger.info("SparseIndex initialized (empty)")
        
    def tokenize(self, text: str) -> list[str]:
        """Simple Indonesian tokenization."""
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        return text.split()
        
    def build_index(self, chunks: list[dict]) -> None:
        """Tokenize and build BM25 index."""
        logger.info("Building BM25 index with %d documents...", len(chunks))
        start_time = time.time()
        
        self.corpus_data = chunks
        tokenized_corpus = [self.tokenize(c['text']) for c in chunks]
        
        if tokenized_corpus:
            self.bm25 = BM25Okapi(tokenized_corpus)
            
        elapsed = time.time() - start_time
        total_tokens = sum(len(t) for t in tokenized_corpus)
        vocab = set(token for doc in tokenized_corpus for token in doc)
        logger.info("BM25 index built in %.2fs (docs=%d, total_tokens=%d, vocab_size=%d)",
                    elapsed, len(chunks), total_tokens, len(vocab))
        
    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        """Query BM25."""
        if not self.bm25:
            logger.warning("BM25 query called but index is empty, returning empty results")
            return []
        
        truncated_query = query_text[:80] + "..." if len(query_text) > 80 else query_text
        logger.info("Sparse query (top_k=%d): '%s'", top_k, truncated_query)
        
        start_time = time.time()
        tokenized_query = self.tokenize(query_text)
        scores = self.bm25.get_scores(tokenized_query)
        
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            chunk = self.corpus_data[idx]
            results.append({
                "id": chunk["id"],
                "text": chunk["text"],
                "score": scores[idx],
                "metadata": chunk.get("metadata", {})
            })
        
        elapsed = time.time() - start_time
        top_score = results[0]['score'] if results else 0.0
        logger.info("Sparse query returned %d results in %.3fs (top_score=%.4f)",
                    len(results), elapsed, top_score)
        return results
