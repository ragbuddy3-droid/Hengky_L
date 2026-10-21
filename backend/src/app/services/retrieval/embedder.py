"""Text embeddings from the DeepInfra OpenAI-compatible API, so no model runs locally."""

import logging

import numpy as np
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 64  # texts per request; a whole book is embedded in a handful of calls


class DeepInfraEmbedder:
    """Drop-in for the SentenceTransformer.encode() calls the app makes."""

    def __init__(self, model_name: str):
        settings = get_settings()
        api_key = settings.DEEPINFRA_API_KEY
        if not api_key:
            logger.warning("DEEPINFRA_API_KEY is not configured in .env. Embedding calls will fail.")
        self.model_name = model_name
        self._client = OpenAI(
            api_key=api_key or "sk-dummy-key",
            base_url=settings.DEEPINFRA_BASE_URL or "https://api.deepinfra.com/v1/openai",
            timeout=settings.LLM_REQUEST_TIMEOUT,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    def encode(self, texts: list[str], normalize_embeddings: bool = True, **_: object) -> np.ndarray:
        """Embed texts in order; rows are L2-normalized when requested."""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            # The API rejects empty strings, which can come from blank chunks
            batch = [t if t.strip() else " " for t in texts[i : i + _BATCH_SIZE]]
            resp = self._client.embeddings.create(model=self.model_name, input=batch, encoding_format="float")
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        embeddings = np.asarray(vectors, dtype=np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / np.where(norms == 0, 1.0, norms)
        return embeddings
