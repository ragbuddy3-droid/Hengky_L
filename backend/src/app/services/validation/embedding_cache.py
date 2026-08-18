"""In-memory embedding cache to avoid redundant SentenceTransformer encode calls."""

import hashlib
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """In-memory cache for text embeddings with simple LRU eviction."""

    def __init__(self, model: Any, max_entries: int = 500):
        self._model = model
        self._cache: dict[str, np.ndarray] = {}
        self._max_entries = max_entries

    def encode(self, text: str) -> np.ndarray:
        """Encode single text with caching."""
        key = hashlib.md5(text.strip().encode("utf-8")).hexdigest()
        if key not in self._cache:
            if len(self._cache) >= self._max_entries:
                # Evict oldest ~10%
                for old_key in list(self._cache.keys())[: self._max_entries // 10]:
                    del self._cache[old_key]
            self._cache[key] = self._model.encode(
                [text.strip()], normalize_embeddings=True
            )[0]
        return self._cache[key]

    def encode_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Encode multiple texts, using cache where possible."""
        results: list[tuple[int, np.ndarray]] = []
        to_encode: list[str] = []
        to_encode_indices: list[int] = []

        for i, text in enumerate(texts):
            key = hashlib.md5(text.strip().encode("utf-8")).hexdigest()
            if key in self._cache:
                results.append((i, self._cache[key]))
            else:
                to_encode.append(text.strip())
                to_encode_indices.append(i)

        if to_encode:
            new_embeddings = self._model.encode(to_encode, normalize_embeddings=True)
            for idx, emb in zip(to_encode_indices, new_embeddings):
                key = hashlib.md5(texts[idx].strip().encode("utf-8")).hexdigest()
                self._cache[key] = emb
                results.append((idx, emb))

        results.sort(key=lambda x: x[0])
        return [emb for _, emb in results]

    def clear(self):
        """Clear all cached embeddings."""
        self._cache.clear()
