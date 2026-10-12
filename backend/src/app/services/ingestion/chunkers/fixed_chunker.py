"""Pure fixed-size chunker (sliding character window) with pedagogical and chapter metadata enrichment."""

import logging
from bisect import bisect_right
from dataclasses import dataclass

from app.services.ingestion.chunkers.classifiers import (
    classify_chunk_category,
    extract_chapter_and_heading,
)
from app.services.ingestion.extractor import PageContent

logger = logging.getLogger(__name__)

PAGE_SEPARATOR = "\n\n"


@dataclass
class ChunkResult:
    """Standardized chunk representation with complete structural and page metadata."""
    text: str
    category: str  # 'materi_pokok' | 'uraian_materi' | 'studi_kasus' | 'aktivitas_diskusi' | 'rangkuman'
    section_heading: str | None = None
    chapter: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    section_type: str | None = None


class FixedChunker:
    """
    Pure fixed-size chunker: a sliding window of exactly `chunk_size` characters,
    advancing by `chunk_size - chunk_overlap` characters. No separator-aware splitting,
    no per-page boundaries, and no fragment filtering. Only the final chunk may be shorter.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.step = chunk_size - chunk_overlap
        logger.info("FixedChunker initialized (chunk_size=%d, chunk_overlap=%d)", chunk_size, chunk_overlap)

    def _windows(self, text: str) -> list[tuple[int, str]]:
        """Return (start_offset, slice) pairs covering the whole text with fixed overlap."""
        windows: list[tuple[int, str]] = []
        n = len(text)
        start = 0
        while start < n:
            end = min(start + self.chunk_size, n)
            windows.append((start, text[start:end]))
            if end >= n:
                break
            start += self.step
        return windows

    def chunk_pages(self, pages: list[PageContent]) -> list[ChunkResult]:
        """
        Concatenate all pages into one stream and cut it into fixed-size windows.
        Each chunk is attributed to the page (and page chapter) where it starts.
        """
        pages = [p for p in pages if p.text and p.text.strip()]
        if not pages:
            return []

        # Build the document stream and record each page's start offset
        offsets: list[int] = []
        parts: list[str] = []
        pos = 0
        for page in pages:
            offsets.append(pos)
            parts.append(page.text)
            pos += len(page.text) + len(PAGE_SEPARATOR)
        full_text = PAGE_SEPARATOR.join(parts)

        results: list[ChunkResult] = []
        current_chapter: str | None = None
        current_heading: str | None = None

        for start, content in self._windows(full_text):
            if not content.strip():
                continue

            page = pages[bisect_right(offsets, start) - 1]

            # Inherit chapter from page metadata (populated from TOC & page openers)
            if page.chapter and page.chapter != current_chapter:
                current_chapter = page.chapter
                current_heading = None  # Reset heading on chapter transition

            extracted_ch, current_heading = extract_chapter_and_heading(
                content, current_chapter, current_heading
            )
            if extracted_ch and extracted_ch != current_chapter:
                current_chapter = extracted_ch
                current_heading = None

            category = classify_chunk_category(content)
            results.append(
                ChunkResult(
                    text=content,
                    category=category,
                    section_heading=current_heading,
                    chapter=current_chapter,
                    page_number=page.page_number,
                    chunk_index=len(results),
                    section_type=category,
                )
            )

        logger.info("FixedChunker produced %d chunks from %d pages", len(results), len(pages))
        return results

    def chunk(self, text: str, page_number: int | None = 1) -> list[ChunkResult]:
        """Split raw text into fixed-size chunks with chapter and pedagogical metadata."""
        if not text or not text.strip():
            logger.warning("FixedChunker received empty text.")
            return []

        chunks = self.chunk_pages([PageContent(page_number=page_number or 1, text=text)])
        logger.info("FixedChunker produced %d chunks from %d characters", len(chunks), len(text))
        return chunks
