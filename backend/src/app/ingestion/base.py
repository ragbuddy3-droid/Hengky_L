"""Base chunker interface and data models."""
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass

class PedagogicalCategory(Enum):
    KONSEP = "KONSEP"
    NARASI = "NARASI"
    INSTRUKSI = "INSTRUKSI"
    EVALUASI = "EVALUASI"

@dataclass
class ChunkResult:
    text: str
    category: PedagogicalCategory
    section_heading: str
    chapter: str

class BaseChunker(ABC):
    """Abstract base class for document chunkers."""

    @abstractmethod
    def chunk(self, text: str, max_chunk_size: int = 1000) -> list[ChunkResult]:
        """Split text into structured ChunkResult objects.
        
        Args:
            text: Cleaned full text of the document.
            max_chunk_size: Target maximum chunk size in characters.
            
        Returns:
            List of ChunkResult objects.
        """
        pass
