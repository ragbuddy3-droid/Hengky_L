"""Fixed-size chunker using LangChain RecursiveCharacterTextSplitter with pedagogical and chapter metadata enrichment."""

import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

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
    category: str  # 'materi_pokok' | 'uraian_materi' | 'studi_kasus' | 'aktivitas_diskusi' | 'rangkuman'
    section_heading: str | None = None
    chapter: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    section_type: str | None = None


class FixedChunker:
    """
    Fixed-size text chunker using LangChain RecursiveCharacterTextSplitter.
    Accurately maps textbook structure (chapter, heading, page number, and pedagogical category).
    """

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

    def chunk_pages(self, pages: list[PageContent]) -> list[ChunkResult]:
        """
        Split list of PageContent objects into fixed-size chunks while preserving
        exact chapter mapping, section headings, page numbers, and pedagogical categories.
        """
        if not pages:
            return []

        results: list[ChunkResult] = []
        current_chapter: str | None = None
        current_heading: str | None = None
        chunk_idx = 0

        for page in pages:
            # Inherit chapter from page metadata (populated from TOC & page openers)
            if getattr(page, "chapter", None):
                if current_chapter != page.chapter:
                    current_chapter = page.chapter
                    current_heading = None  # Reset heading on chapter transition

            page_text = page.text.strip()
            if not page_text:
                continue

            # Split page text into fixed-size pieces
            pieces = self.splitter.split_text(page_text)

            for piece in pieces:
                content = piece.strip()
                if not content:
                    continue

                # Extract or update chapter & heading from the chunk content
                extracted_ch, current_heading = extract_chapter_and_heading(
                    content, current_chapter, current_heading
                )
                if extracted_ch and extracted_ch != current_chapter:
                    current_chapter = extracted_ch
                    current_heading = None

                # Fallback to page.chapter if current_chapter is still unassigned
                if not current_chapter and getattr(page, "chapter", None):
                    current_chapter = page.chapter

                # Avoid standalone tiny fragments (< 10 words) if we already have chunks
                if len(content.split()) < 10 and results:
                    continue

                category = classify_chunk_category(content)

                results.append(
                    ChunkResult(
                        text=content,
                        category=category,
                        section_heading=current_heading,
                        chapter=current_chapter,
                        page_number=page.page_number,
                        chunk_index=chunk_idx,
                        section_type=category,
                    )
                )
                chunk_idx += 1

        logger.info("FixedChunker produced %d chunks from %d pages", len(results), len(pages))
        return results

    def chunk(
        self,
        text: str,
        page_number: int | None = 1,
        max_chunk_size: int | None = None,
    ) -> list[ChunkResult]:
        """Split text into fixed chunks with chapter and pedagogical metadata."""
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

        pieces = splitter.split_text(text)
        results: list[ChunkResult] = []
        current_chapter: str | None = None
        current_heading: str | None = None
        chunk_idx = 0

        for piece in pieces:
            content = piece.strip()
            if not content or (len(content.split()) < 10 and results):
                continue

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
                    page_number=page_number or 1,
                    chunk_index=chunk_idx,
                    section_type=category,
                )
            )
            chunk_idx += 1

        logger.info("FixedChunker produced %d chunks from %d characters", len(results), len(text))
        return results
