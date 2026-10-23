"""Cached FixedChunker built from the chunking settings."""

from functools import cache

from app.core.config import get_settings
from app.services.ingestion.chunkers.fixed_chunker import ChunkResult, FixedChunker
from app.services.ingestion.extractor import PageContent


@cache
def get_chunker() -> FixedChunker:
    chunking = get_settings().chunking
    return FixedChunker(chunk_size=chunking.fixed_chunk_size, chunk_overlap=chunking.fixed_chunk_overlap)


def chunk_pages(pages: list[PageContent]) -> list[ChunkResult]:
    """Chunk extracted pages, keeping page and chapter metadata."""
    return get_chunker().chunk_pages(pages)
