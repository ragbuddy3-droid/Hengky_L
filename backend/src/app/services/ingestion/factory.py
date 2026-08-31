"""Chunker Factory and Strategy Dispatcher."""

import logging
from enum import StrEnum
from typing import Any

from app.core.config import Settings, get_settings
from app.services.ingestion.chunkers.section_aware_chunker import (
    ChunkResult,
    SectionAwareChunker,
)
from app.services.ingestion.extractor import PageContent

logger = logging.getLogger(__name__)


class ChunkerStrategy(StrEnum):
    SECTION_AWARE = "section_aware"
    FIXED = "fixed"
    SEMANTIC = "semantic"


# Cached chunker instances
_chunker_cache: dict[str, Any] = {}


def get_chunker(
    strategy: str | ChunkerStrategy = ChunkerStrategy.SECTION_AWARE,
    settings: Settings | None = None
) -> SectionAwareChunker:
    """Factory method to retrieve a chunker instance based on strategy."""
    if settings is None:
        settings = get_settings()

    strat_str = strategy.value.lower() if isinstance(strategy, ChunkerStrategy) else str(strategy).lower()

    # Section-aware is the primary strategy for all educational textbooks
    cache_key = f"section_aware_{settings.chunking.target_words_min}_{settings.chunking.target_words_max}_{settings.chunking.overlap_sentences}"
    if cache_key not in _chunker_cache:
        _chunker_cache[cache_key] = SectionAwareChunker(
            target_words_min=settings.chunking.target_words_min,
            target_words_max=settings.chunking.target_words_max,
            overlap_sentences=settings.chunking.overlap_sentences,
        )
    return _chunker_cache[cache_key]


def chunk_text(
    text: str,
    strategy: str | ChunkerStrategy = ChunkerStrategy.SECTION_AWARE,
    settings: Settings | None = None
) -> list[ChunkResult]:
    """Convenience function to chunk text using the section-aware strategy."""
    chunker = get_chunker(strategy, settings=settings)
    return chunker.chunk(text)


def chunk_pages(
    pages: list[PageContent],
    strategy: str | ChunkerStrategy = ChunkerStrategy.SECTION_AWARE,
    settings: Settings | None = None
) -> list[ChunkResult]:
    """Convenience function to chunk extracted PDF PageContent list with page tracking."""
    chunker = get_chunker(strategy, settings=settings)
    return chunker.chunk_pages(pages)
