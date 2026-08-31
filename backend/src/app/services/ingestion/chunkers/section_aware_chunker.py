"""Section-Aware Chunking Strategy for Educational Textbooks."""

import logging
import re
from dataclasses import dataclass

from app.services.ingestion.chunkers.classifiers import (
    classify_chunk_category,
    extract_chapter_and_heading,
)
from app.services.ingestion.extractor import PageContent

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """Standardized chunk representation with complete structural and page metadata."""
    text: str
    category: str  # Backward compatibility: 'materi_pokok' | 'uraian_materi' | 'studi_kasus' | 'aktivitas_diskusi' | 'rangkuman'
    section_heading: str | None = None
    chapter: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    section_type: str | None = None


class SectionAwareChunker:
    """
    Section-Aware and Structure-Aware Chunker designed for elementary school textbooks.
    Splits content along heading hierarchies and paragraph boundaries, maintaining
    cohesive 250-450 word units (~1200-2200 characters) with sentence-level overlap.
    """

    def __init__(
        self,
        target_words_min: int = 200,
        target_words_max: int = 450,
        overlap_sentences: int = 2,
    ):
        self.target_words_min = target_words_min
        self.target_words_max = target_words_max
        self.overlap_sentences = overlap_sentences
        logger.info(
            "SectionAwareChunker initialized (target_words=%d-%d, overlap_sentences=%d)",
            target_words_min, target_words_max, overlap_sentences
        )

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into individual sentences accurately."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def chunk_pages(self, pages: list[PageContent]) -> list[ChunkResult]:
        """Chunk extracted list of PageContent objects with accurate page number and chapter tracking."""
        if not pages:
            return []

        results: list[ChunkResult] = []
        current_chapter: str | None = None
        current_heading: str | None = None
        chunk_idx = 0

        buffer_paragraphs: list[tuple[str, int]] = []
        current_word_count = 0

        for page in pages:
            # Inherit chapter from page metadata if available
            if getattr(page, "chapter", None):
                current_chapter = page.chapter

            page_text = page.text.strip()
            if not page_text:
                continue

            paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]

            for p in paragraphs:
                current_chapter, current_heading = extract_chapter_and_heading(
                    p, current_chapter, current_heading
                )

                p_words = len(p.split())
                if p_words == 0:
                    continue

                if current_word_count + p_words > self.target_words_max and current_word_count >= self.target_words_min:
                    chunk_text = '\n\n'.join(text for text, _ in buffer_paragraphs)
                    first_page = buffer_paragraphs[0][1]
                    sec_type = classify_chunk_category(chunk_text)

                    results.append(
                        ChunkResult(
                            text=chunk_text,
                            category=sec_type,
                            section_heading=current_heading,
                            chapter=current_chapter,
                            page_number=first_page,
                            chunk_index=chunk_idx,
                            section_type=sec_type,
                        )
                    )
                    chunk_idx += 1

                    last_p_text, last_page = buffer_paragraphs[-1]
                    sentences = self._split_into_sentences(last_p_text)
                    overlap_text = ' '.join(sentences[-self.overlap_sentences:]) if len(sentences) >= self.overlap_sentences else last_p_text

                    buffer_paragraphs = [(overlap_text, last_page), (p, page.page_number)]
                    current_word_count = len(overlap_text.split()) + p_words
                else:
                    buffer_paragraphs.append((p, page.page_number))
                    current_word_count += p_words

        if buffer_paragraphs:
            chunk_text = '\n\n'.join(text for text, _ in buffer_paragraphs)
            if len(chunk_text.split()) >= 25 or not results:
                first_page = buffer_paragraphs[0][1]
                sec_type = classify_chunk_category(chunk_text)
                results.append(
                    ChunkResult(
                        text=chunk_text,
                        category=sec_type,
                        section_heading=current_heading,
                        chapter=current_chapter,
                        page_number=first_page,
                        chunk_index=chunk_idx,
                        section_type=sec_type,
                    )
                )

        logger.info("SectionAwareChunker produced %d chunks from %d pages", len(results), len(pages))
        return results

    def chunk(self, text: str, page_number: int | None = 1) -> list[ChunkResult]:
        """Chunk raw text string (convenience interface)."""
        if not text or not text.strip():
            return []
        page = PageContent(page_number=page_number or 1, text=text)
        return self.chunk_pages([page])
