"""Cached LangChain chat models for the DeepInfra OpenAI-compatible API."""

import logging

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_chat_model_cache: dict[tuple[str, float], ChatOpenAI] = {}


def get_chat_model(is_judge: bool = False, temperature: float | None = None) -> ChatOpenAI:
    """Get or create a cached chat model that answers in JSON mode."""
    settings = get_settings()
    model_name = settings.LLM_JUDGE_MODEL if is_judge else settings.LLM_GENERATOR_MODEL
    temp = temperature if temperature is not None else (0.05 if is_judge else 0.3)

    cache_key = (model_name, temp)
    if cache_key in _chat_model_cache:
        return _chat_model_cache[cache_key]

    api_key = settings.DEEPINFRA_API_KEY
    if not api_key:
        logger.warning("DEEPINFRA_API_KEY is not configured in .env. LLM calls will require a valid DeepInfra token.")

    client = ChatOpenAI(
        model=model_name,
        api_key=api_key or "sk-dummy-key",
        base_url=settings.DEEPINFRA_BASE_URL or "https://api.deepinfra.com/v1/openai",
        temperature=temp,
        max_tokens=settings.MAX_TOKENS,  # pyright: ignore[reportCallIssue]  # alias of max_completion_tokens
        timeout=settings.LLM_REQUEST_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
        model_kwargs={"response_format": {"type": "json_object"}},
        default_headers={"HTTP-Referer": "http://localhost:3000", "X-Title": "Soalnya"},
    )
    _chat_model_cache[cache_key] = client
    return client
