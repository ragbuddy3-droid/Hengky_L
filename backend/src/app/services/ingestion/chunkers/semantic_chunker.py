"""Semantic chunker using LangChain SemanticChunker with sentence embeddings."""

import logging
import re

from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings

from app.services.ingestion.chunkers.classifiers import (
    classify_chunk_category,
    extract_chapter_and_heading,
)
from app.services.ingestion.chunkers.fixed_chunker import ChunkResult

logger = logging.getLogger(__name__)


class SemanticChunkerWrapper:
    """Semantic chunker based on embedding distance percentile breakpoints."""

    def __init__(
        self,
        embedding_model_name: str = "BAAI/bge-m3",
        breakpoint_threshold_type: str = "percentile",
        breakpoint_threshold_amount: float = 95.0,
    ):
        self.embedding_model_name = embedding_model_name
        self.breakpoint_threshold_type = breakpoint_threshold_type
        self.breakpoint_threshold_amount = breakpoint_threshold_amount

        logger.info(
            "Initializing SemanticChunkerWrapper (model=%s, breakpoint_type=%s, threshold=%.1f)...",
            embedding_model_name, breakpoint_threshold_type, breakpoint_threshold_amount
        )
        self._embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._splitter = SemanticChunker(
            embeddings=self._embeddings,
            breakpoint_threshold_type=breakpoint_threshold_type,
            breakpoint_threshold_amount=breakpoint_threshold_amount,
        )
        logger.info("SemanticChunkerWrapper ready.")

    def chunk(self, text: str, max_chunk_size: int | None = None) -> list[ChunkResult]:
        """Split text into semantic chunks with pedagogical metadata."""
        if not text or not text.strip():
            logger.warning("SemanticChunker received empty text.")
            return []

        logger.info("Starting semantic chunking on text length: %d chars...", len(text))
        docs = self._splitter.create_documents([text])
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

        logger.info("SemanticChunker produced %d chunks from %d characters", len(results), len(text))
        return results
