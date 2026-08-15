"""Unified LLM Client supporting Groq Cloud API and Ollama."""
import os
import logging
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMClient:
    """Unified client for Chat Completions (Groq API / Ollama)."""

    def __init__(self, provider: str = "groq", groq_api_key: Optional[str] = None, ollama_base_url: str = "http://localhost:11434"):
        self.provider = (provider or "groq").lower()
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.ollama_base_url = ollama_base_url
        self._httpx_client: Optional[httpx.AsyncClient] = None
        self._ollama_client = None

        logger.info("LLMClient initialized (provider=%s, groq_key_present=%s)",
                    self.provider, bool(self.groq_api_key))

    async def chat(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Perform chat completion with auto-routing based on provider."""
        if self.provider == "groq" or (self.groq_api_key and self.provider != "ollama"):
            return await self._chat_groq(model, messages, **kwargs)
        else:
            return await self._chat_ollama(model, messages, **kwargs)

    async def _chat_groq(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not found, falling back to Ollama")
            return await self._chat_ollama(model, messages, **kwargs)

        # Default Groq model fallback if local tag like 'qwen2.5:3b' is passed
        groq_model = model
        if ":" in model or "qwen" in model.lower() or "14b" in model.lower() or "3b" in model.lower():
            groq_model = "qwen/qwen3.6-27b"

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": groq_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_completion_tokens": kwargs.get("max_tokens", 4096),
            "reasoning_format": "hidden",
        }

        logger.info("Calling Groq Cloud API (model=%s, messages=%d)...", groq_model, len(messages))

        if self._httpx_client is None or self._httpx_client.is_closed:
            self._httpx_client = httpx.AsyncClient(timeout=60.0)

        import asyncio
        # Exponential backoff: 10s, 20s, 40s, 60s — baca Retry-After header jika ada
        _RETRY_WAITS = [10.0, 20.0, 40.0, 60.0]
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = await self._httpx_client.post(url, headers=headers, json=payload)
                if response.status_code == 429 and attempt < max_retries - 1:
                    # Baca header Retry-After jika Groq menyediakan
                    retry_after = response.headers.get("retry-after") or response.headers.get("x-ratelimit-reset-requests")
                    if retry_after:
                        try:
                            wait_sec = float(retry_after)
                        except (ValueError, TypeError):
                            wait_sec = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                    else:
                        wait_sec = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                    logger.warning(
                        "Groq API 429 Rate Limit. Waiting %.1fs before retry (attempt %d/%d)...",
                        wait_sec, attempt + 1, max_retries
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("Groq API response received (%d chars)", len(content))
                return {"message": {"content": content}}
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_sec = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                    logger.warning("Groq 429 (HTTPStatusError). Waiting %.1fs (attempt %d/%d)...",
                                   wait_sec, attempt + 1, max_retries)
                    await asyncio.sleep(wait_sec)
                    continue
                logger.error("Groq API call failed after %d attempts: %s", attempt + 1, e)
                raise
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("Groq API call failed after %d attempts: %s", max_retries, e)
                    raise

    async def _chat_ollama(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        import ollama
        logger.info("Calling Ollama API (host=%s, model=%s)...", self.ollama_base_url, model)
        if self._ollama_client is None:
            self._ollama_client = ollama.AsyncClient(host=self.ollama_base_url)
        return await self._ollama_client.chat(model=model, messages=messages)
