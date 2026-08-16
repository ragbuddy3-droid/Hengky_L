"""Fixed-size chunker using LangChain RecursiveCharacterTextSplitter with pedagogical metadata enrichment."""

import logging
import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

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

    def _classify_category(self, text: str) -> str:
        """Classify text chunk into pedagogical categories."""
        lower = text.lower()
        eval_keywords = ["latihan", "soal", "uji kompetensi", "evaluasi", "jawablah", "pilihlah jawaban", "tugas individu"]
        instr_keywords = ["amati", "lakukan", "diskusikan", "buatlah", "tugas kelompok", "ayo mencoba", "petunjuk", "langkah"]
        konsep_patterns = [r'\b(adalah|merupakan|yaitu|artinya|didefinisikan sebagai|terdiri atas|fungsi dari|organ|sistem)\b']

        if any(k in lower for k in eval_keywords):
            return "Evaluasi"
        if any(k in lower for k in instr_keywords):
            return "Instruksi"
        if any(re.search(pat, lower) for pat in konsep_patterns):
            return "Konsep"
        return "Narasi"

    def _extract_chapter_and_heading(self, text: str, prev_chapter: str | None, prev_heading: str | None):
        """Extract or inherit chapter and heading from text lines."""
        chapter = prev_chapter
        heading = prev_heading

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[:3]:
            # Chapter pattern
            chap_match = re.search(r'\b(Bab|Chapter|Unit|Pembelajaran|Modul)\s+([\w\d]+)', line, re.IGNORECASE)
            if chap_match:
                chapter = chap_match.group(0)

            # Section heading pattern (short line, uppercase or title-case, no trailing period)
            if (
                2 <= len(line.split()) <= 8
                and not line.endswith((".", ":", "?", "!"))
                and not re.search(r'^(gambar|tabel|sumber)\b', line, re.IGNORECASE)
            ):
                heading = line

        return chapter, heading


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

            current_chapter, current_heading = self._extract_chapter_and_heading(content, current_chapter, current_heading)
            category = self._classify_category(content)

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
