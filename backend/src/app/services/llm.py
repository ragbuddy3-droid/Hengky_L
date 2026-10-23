"""Cached LangChain chat models for the DeepInfra OpenAI-compatible API."""

import logging
from functools import cache
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

def deepinfra_client_kwargs() -> dict[str, Any]:
    """Connection settings shared by the chat and embedding clients."""
    settings = get_settings()
    api_key = settings.llm.deepinfra_api_key
    if not api_key:
        logger.warning("DEEPINFRA_API_KEY is not configured in .env; DeepInfra calls will fail.")
    return {
        "api_key": api_key or "sk-dummy-key",
        "base_url": settings.llm.deepinfra_base_url,
        "timeout": settings.llm.request_timeout,
        "max_retries": settings.llm.max_retries,
    }


def get_chat_model(is_judge: bool = False, temperature: float | None = None) -> ChatOpenAI:
    """Cached chat model (per model and temperature) that answers in JSON mode."""
    settings = get_settings()
    model_name = settings.llm.judge_model if is_judge else settings.llm.generator_model
    temp = temperature if temperature is not None else (0.05 if is_judge else 0.3)
    return _chat_model(model_name, temp)


@cache
def _chat_model(model_name: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        max_tokens=get_settings().llm.max_tokens,  # pyright: ignore[reportCallIssue]  # alias of max_completion_tokens
        model_kwargs={"response_format": {"type": "json_object"}},
        **deepinfra_client_kwargs(),
    )
