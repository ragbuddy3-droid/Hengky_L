"""Chunker Factory and Strategy Dispatcher."""

from enum import Enum
import logging
from typing import Union, Optional, List

from app.core.config import get_settings, Settings
from app.services.ingestion.chunkers.fixed_chunker import FixedChunker, ChunkResult
from app.services.ingestion.chunkers.semantic_chunker import SemanticChunkerWrapper

logger = logging.getLogger(__name__)


class ChunkerStrategy(str, Enum):
    FIXED = "fixed"
    SEMANTIC = "semantic"


# Cached chunker instances
_chunker_cache = {}


def get_chunker(
    strategy: Union[str, ChunkerStrategy] = ChunkerStrategy.FIXED,
    settings: Optional[Settings] = None
) -> Union[FixedChunker, SemanticChunkerWrapper]:
    """Factory method to retrieve a chunker instance based on strategy."""
    if settings is None:
        settings = get_settings()

    if isinstance(strategy, ChunkerStrategy):
        strat_str = strategy.value.lower()
    else:
        strat_str = str(strategy).lower()

    if strat_str in ("semantic", "semantic_chunking"):
        cache_key = f"semantic_{settings.llm.embedding_model}_{settings.chunking.semantic_breakpoint_threshold}"
        if cache_key not in _chunker_cache:
            _chunker_cache[cache_key] = SemanticChunkerWrapper(
                embedding_model_name=settings.llm.embedding_model,
                breakpoint_threshold_type=settings.chunking.semantic_breakpoint_type,
                breakpoint_threshold_amount=settings.chunking.semantic_breakpoint_threshold,
            )
        return _chunker_cache[cache_key]
    else:
        # Default is "fixed"
        cache_key = f"fixed_{settings.chunking.fixed_chunk_size}_{settings.chunking.fixed_chunk_overlap}"
        if cache_key not in _chunker_cache:
            _chunker_cache[cache_key] = FixedChunker(
                chunk_size=settings.chunking.fixed_chunk_size,
                chunk_overlap=settings.chunking.fixed_chunk_overlap,
            )
        return _chunker_cache[cache_key]


def chunk_text(
    text: str,
    strategy: Union[str, ChunkerStrategy] = ChunkerStrategy.FIXED,
    settings: Optional[Settings] = None
) -> List[ChunkResult]:
    """Convenience function to chunk text using the specified strategy."""
    chunker = get_chunker(strategy, settings=settings)
    return chunker.chunk(text)
