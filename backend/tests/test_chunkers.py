"""Test suite for modular chunkers and strategy factory."""
import pytest
from app.ingestion import (
    BaseChunker,
    StructureChunker,
    PAChunker,
    ChunkerStrategy,
    get_chunker,
    chunk_text
)

SAMPLE_TEXT = """
Bab 1: Mengenal Alam Sekitar

A. Pengertian Ekosistem
Ekosistem adalah hubungan timbal balik antara makhluk hidup dengan lingkungannya. Lingkungan hidup terdiri atas komponen biotik dan komponen abiotik. Komponen biotik meliputi manusia, hewan, dan tumbuhan. Sedangkan komponen abiotik meliputi air, tanah, udara, dan cahaya matahari.

B. Jenis-Jenis Ekosistem
Ekosistem dapat dibedakan menjadi dua kelompok utama, yaitu ekosistem alami dan ekosistem buatan. Contoh ekosistem alami adalah hutan hujan tropis, sungai, dan laut. Contoh ekosistem buatan adalah sawah, kolam, dan akuarium.

Mari Mencoba
1. Amatilah lingkungan di sekitar rumahmu!
2. Catatlah komponen biotik dan abiotik yang kamu temukan dalam buku catatan!

Uji Pemahaman
Jawablah pertanyaan berikut dengan tepat:
1. Apa yang dimaksud dengan ekosistem?
2. Sebutkan 3 contoh ekosistem alami dan 3 contoh ekosistem buatan!
"""

def test_factory():
    chunker_struct = get_chunker("structured")
    assert isinstance(chunker_struct, StructureChunker)
    
    chunker_pac = get_chunker("pac")
    assert isinstance(chunker_pac, PAChunker)
    
    chunker_enum = get_chunker(ChunkerStrategy.STRUCTURED)
    assert isinstance(chunker_enum, StructureChunker)

def test_structure_chunker():
    chunks = chunk_text(SAMPLE_TEXT, max_chunk_size=500, strategy="structured")
    assert len(chunks) > 0
    assert any("Pengertian Ekosistem" in c.section_heading for c in chunks)

def test_pac_chunker():
    chunks = chunk_text(SAMPLE_TEXT, max_chunk_size=500, strategy="pac")
    assert len(chunks) > 0

if __name__ == "__main__":
    test_factory()
    test_structure_chunker()
    test_pac_chunker()
    print("ALL TESTS PASSED SUCCESSFULLY!")
