"""Chunking package - Fixed Chunker only."""
from app.services.ingestion.chunkers.classifiers import (
    classify_chunk_category,
    extract_chapter_and_heading,
)
from app.services.ingestion.chunkers.fixed_chunker import ChunkResult, FixedChunker

__all__ = [
    "ChunkResult",
    "FixedChunker",
    "classify_chunk_category",
    "extract_chapter_and_heading",
]

