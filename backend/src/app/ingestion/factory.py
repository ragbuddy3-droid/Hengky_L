"""Chunker Factory and Strategy Dispatcher."""
from enum import Enum
import logging
from typing import Union

from app.ingestion.base import BaseChunker, ChunkResult
from app.ingestion.structure_chunker import StructureChunker
from app.ingestion.pac_chunker import PAChunker

logger = logging.getLogger(__name__)

class ChunkerStrategy(str, Enum):
    STRUCTURED = "structured"
    PAC = "pac"

def get_chunker(strategy: Union[str, ChunkerStrategy] = ChunkerStrategy.STRUCTURED) -> BaseChunker:
    """Factory method to retrieve a chunker instance based on strategy.
    
    Args:
        strategy: 'structured' (default) or 'pac'.
        
    Returns:
        An instance of BaseChunker (StructureChunker or PAChunker).
    """
    if isinstance(strategy, ChunkerStrategy):
        strat_str = strategy.value.lower()
    else:
        strat_str = str(strategy).lower()

    if strat_str in ("structured", "structure", "structure_chunking"):
        return StructureChunker()
    elif strat_str in ("pac", "pa_chunking", "pedagogical"):
        return PAChunker()
    else:
        logger.warning("Unknown chunker strategy '%s', falling back to 'structured'", strategy)
        return StructureChunker()

def chunk_text(
    text: str,
    max_chunk_size: int = 1000,
    strategy: Union[str, ChunkerStrategy] = ChunkerStrategy.STRUCTURED
) -> list[ChunkResult]:
    """Convenience function to chunk text using the specified strategy.
    
    Args:
        text: Raw cleaned text to chunk.
        max_chunk_size: Target maximum chunk size.
        strategy: Chunking strategy ('structured' or 'pac').
        
    Returns:
        List of ChunkResult objects.
    """
    chunker = get_chunker(strategy)
    return chunker.chunk(text, max_chunk_size=max_chunk_size)
