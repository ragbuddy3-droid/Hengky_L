"""Ingestion module providing text extraction and modular chunking strategies."""
from app.ingestion.extractor import extract_text_from_pdf, clean_text, process_pdf
from app.ingestion.base import BaseChunker, ChunkResult, PedagogicalCategory
from app.ingestion.structure_chunker import StructureChunker
from app.ingestion.pac_chunker import PAChunker
from app.ingestion.factory import ChunkerStrategy, get_chunker, chunk_text

__all__ = [
    "extract_text_from_pdf",
    "clean_text",
    "process_pdf",
    "BaseChunker",
    "ChunkResult",
    "PedagogicalCategory",
    "StructureChunker",
    "PAChunker",
    "ChunkerStrategy",
    "get_chunker",
    "chunk_text",
]
