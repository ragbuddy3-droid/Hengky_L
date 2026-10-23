"""Sparse lexical retrieval using BM25 Okapi with Indonesian text tokenization."""

import logging
import string
from typing import Any

from rank_bm25 import BM25Okapi

# Standard Indonesian stopwords to filter out non-discriminative filler terms from BM25
INDONESIAN_STOPWORDS = {
    "yang", "di", "dari", "pada", "untuk", "dan", "atau", "adalah", "yaitu", "ini", "itu",
    "dengan", "dalam", "ke", "oleh", "sebagai", "akan", "telah", "sudah", "dapat", "bisa",
    "kalian", "kamu", "kita", "mereka", "dia", "ia", "secara", "karena", "sehingga",
    "tersebut", "tentang", "juga", "saja", "ada", "tidak", "bukan", "hanya", "bagi",
    "antara", "saat", "ketika", "kemudian", "lalu", "lebih", "sangat", "hal", "suatu",
}

logger = logging.getLogger(__name__)


class SparseIndex:
    """Lexical index based on BM25 Okapi for keyword-based retrieval."""

    def __init__(self):
        self.bm25: BM25Okapi | None = None
        self.chunks: list[dict[str, Any]] = []
        self._punct_table = str.maketrans("", "", string.punctuation)

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text into lowercase words stripped of punctuation and stopwords."""
        if not text:
            return []
        words = text.translate(self._punct_table).lower().split()
        return [w for w in words if len(w) > 1 and w not in INDONESIAN_STOPWORDS]

    def build_index(self, chunks: list[dict[str, Any]]) -> None:
        """Build BM25 index from document chunks."""
        self.chunks = chunks
        if not chunks:
            logger.warning("SparseIndex: empty chunks received for building BM25 index.")
            self.bm25 = None
            return

        corpus = [self.tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(corpus)
        logger.info("SparseIndex built successfully with %d chunks.", len(chunks))

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Query BM25 index and return top-k matches."""
        if not self.bm25 or not self.chunks or not query_text.strip():
            return []

        tokens = self.tokenize(query_text)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results: list[dict[str, Any]] = []
        for idx in ranked_indices[:top_k]:
            score = float(scores[idx])
            if score <= 0.0 and len(results) >= 1:
                # Skip zero-score matches if we already have non-zero results
                continue

            chunk = self.chunks[idx]
            results.append({
                "id": chunk["id"],
                "text": chunk["text"],
                "score": score,
                "metadata": chunk.get("metadata", {}),
            })

        return results
