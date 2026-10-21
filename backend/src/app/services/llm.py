"""Cached LangChain chat models for the DeepInfra OpenAI-compatible API."""

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_chat_model_cache: dict[tuple[str, float], ChatOpenAI] = {}


def deepinfra_client_kwargs() -> dict[str, Any]:
    """Connection settings shared by the chat and embedding clients."""
    settings = get_settings()
    api_key = settings.DEEPINFRA_API_KEY
    if not api_key:
        logger.warning("DEEPINFRA_API_KEY is not configured in .env; DeepInfra calls will fail.")
    return {
        "api_key": api_key or "sk-dummy-key",
        "base_url": settings.DEEPINFRA_BASE_URL,
        "timeout": settings.LLM_REQUEST_TIMEOUT,
        "max_retries": settings.LLM_MAX_RETRIES,
    }


def get_chat_model(is_judge: bool = False, temperature: float | None = None) -> ChatOpenAI:
    """Get or create a cached chat model that answers in JSON mode."""
    settings = get_settings()
    model_name = settings.LLM_JUDGE_MODEL if is_judge else settings.LLM_GENERATOR_MODEL
    temp = temperature if temperature is not None else (0.05 if is_judge else 0.3)

    cache_key = (model_name, temp)
    if cache_key in _chat_model_cache:
        return _chat_model_cache[cache_key]

    client = ChatOpenAI(
        model=model_name,
        temperature=temp,
        max_tokens=settings.MAX_TOKENS,  # pyright: ignore[reportCallIssue]  # alias of max_completion_tokens
        model_kwargs={"response_format": {"type": "json_object"}},
        **deepinfra_client_kwargs(),
    )
    _chat_model_cache[cache_key] = client
    return client
