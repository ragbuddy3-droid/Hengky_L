"""Fixed-size chunker using LangChain RecursiveCharacterTextSplitter with pedagogical metadata enrichment."""

import logging
import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.ingestion.chunkers.classifiers import (
    classify_chunk_category,
    extract_chapter_and_heading,
)

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """Standardized chunk representation across all chunkers."""
    text: str
    category: str  # "Konsep" | "Narasi" | "Instruksi" | "Evaluasi"
    section_heading: str | None = None
    chapter: str | None = None


class FixedChunker:
    """Fixed-size text chunker using hierarchical recursive character splitting."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""],
            length_function=len,
        )
        logger.info("FixedChunker initialized (chunk_size=%d, chunk_overlap=%d)", chunk_size, chunk_overlap)

    def chunk(self, text: str, max_chunk_size: int | None = None) -> list[ChunkResult]:
        """Split text into chunks with pedagogical metadata."""
        if not text or not text.strip():
            logger.warning("FixedChunker received empty text.")
            return []

        splitter = self.splitter
        if max_chunk_size and max_chunk_size != self.chunk_size:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""],
                length_function=len,
            )

        docs = splitter.create_documents([text])
        results: list[ChunkResult] = []
        current_chapter: str | None = None
        current_heading: str | None = None

        for doc in docs:
            content = doc.page_content.strip()
            if not content or len(content.split()) < 10:
                continue

            current_chapter, current_heading = extract_chapter_and_heading(content, current_chapter, current_heading)
            category = classify_chunk_category(content)

            results.append(
                ChunkResult(
                    text=content,
                    category=category,
                    section_heading=current_heading,
                    chapter=current_chapter,
                )
            )

        logger.info("FixedChunker produced %d chunks from %d characters", len(results), len(text))
        return results
