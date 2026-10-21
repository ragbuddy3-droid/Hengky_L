"""Cached FixedChunker built from the chunking settings."""

from app.core.config import get_settings
from app.services.ingestion.chunkers.fixed_chunker import ChunkResult, FixedChunker
from app.services.ingestion.extractor import PageContent

_chunker_cache: dict[tuple[int, int], FixedChunker] = {}


def get_chunker() -> FixedChunker:
    chunking = get_settings().chunking
    key = (chunking.fixed_chunk_size, chunking.fixed_chunk_overlap)
    if key not in _chunker_cache:
        _chunker_cache[key] = FixedChunker(chunk_size=key[0], chunk_overlap=key[1])
    return _chunker_cache[key]


def chunk_pages(pages: list[PageContent]) -> list[ChunkResult]:
    """Chunk extracted pages, keeping page and chapter metadata."""
    return get_chunker().chunk_pages(pages)
