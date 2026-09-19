"""Chunker Factory and Strategy Dispatcher (Fixed Chunking)."""

import logging
from enum import StrEnum
from typing import Any

from app.core.config import Settings, get_settings
from app.services.ingestion.chunkers.fixed_chunker import (
    ChunkResult,
    FixedChunker,
)
from app.services.ingestion.extractor import PageContent

logger = logging.getLogger(__name__)


class ChunkerStrategy(StrEnum):
    FIXED = "fixed"


# Cached chunker instances
_chunker_cache: dict[str, Any] = {}


def get_chunker(
    strategy: str | ChunkerStrategy = ChunkerStrategy.FIXED,
    settings: Settings | None = None
) -> FixedChunker:
    """Factory method to retrieve the FixedChunker instance."""
    if settings is None:
        settings = get_settings()

    chunk_size = getattr(settings.chunking, "fixed_chunk_size", 1000)
    chunk_overlap = getattr(settings.chunking, "fixed_chunk_overlap", 150)
    cache_key = f"fixed_{chunk_size}_{chunk_overlap}"

    if cache_key not in _chunker_cache:
        _chunker_cache[cache_key] = FixedChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    return _chunker_cache[cache_key]


def chunk_text(
    text: str,
    strategy: str | ChunkerStrategy = ChunkerStrategy.FIXED,
    settings: Settings | None = None
) -> list[ChunkResult]:
    """Convenience function to chunk text using FixedChunker."""
    chunker = get_chunker(strategy, settings=settings)
    return chunker.chunk(text)


def chunk_pages(
    pages: list[PageContent],
    strategy: str | ChunkerStrategy = ChunkerStrategy.FIXED,
    settings: Settings | None = None
) -> list[ChunkResult]:
    """Convenience function to chunk extracted PDF PageContent list with page tracking using FixedChunker."""
    chunker = get_chunker(strategy, settings=settings)
    return chunker.chunk_pages(pages)

