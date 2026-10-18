"""Comprehensive unit and regression tests for Chapter Extraction, Section Heading Scoping, Rubric Filtering, and Context Traceability."""

from app.services.ingestion.chunkers.classifiers import (
    SECTION_HEADING_REGEX,
)
from app.services.ingestion.chunkers.fixed_chunker import FixedChunker
from app.services.ingestion.extractor import (
    PageContent,
    extract_chapter_from_raw_page,
)
from app.services.retrieval.hybrid_search import is_exercise_or_instruction_chunk


def test_extract_chapter_from_running_headers():
    """Verify running header format 'Bab X | Judul Bab 123' is accurately parsed into structured chapter string."""
    raw_p1 = "Bab 1 | Makanan Bergizi untuk Kesehatan Pencernaanmu 3\nMulut merupakan organ pertama..."
    chap1 = extract_chapter_from_raw_page(raw_p1)
    assert chap1 == "Bab 1: Makanan Bergizi untuk Kesehatan Pencernaanmu"

    raw_p5 = "Bab 5 | Energi untuk Masa Depan 139\nEnergi alternatif sangat penting..."
    chap5 = extract_chapter_from_raw_page(raw_p5)
    assert chap5 == "Bab 5: Energi untuk Masa Depan"

    raw_p6 = "Bab 6 | Mengembara di Jagat Raya 169\nSistem tata surya kita terdiri atas..."
    chap6 = extract_chapter_from_raw_page(raw_p6)
    assert chap6 == "Bab 6: Mengembara di Jagat Raya"


def test_extract_chapter_from_opener_title():
    """Verify chapter title page opener without pipe delimiter is parsed."""
    raw_opener = "BAB 2: Tarik dan Embuskan\nOrgan pernapasan manusia..."
    chap2 = extract_chapter_from_raw_page(raw_opener)
    assert chap2 == "Bab 2: Tarik dan Embuskan"


def test_section_heading_regex_rejects_numbered_exercises():
    """SECTION_HEADING_REGEX must strictly match real section headings and REJECT numbered exercise lists."""
    valid_heading_1 = "Topik A: Cara Kerja Sistem Pencernaan"
    valid_heading_2 = "A. Organ-Organ Pencernaan"
    valid_heading_3 = "B. Makanan Sehat untuk Tubuhku"
    valid_heading_4 = "Bagian C: Gaya Hidup Sehat"

    assert SECTION_HEADING_REGEX.match(valid_heading_1) is not None
    assert SECTION_HEADING_REGEX.match(valid_heading_2) is not None
    assert SECTION_HEADING_REGEX.match(valid_heading_3) is not None
    assert SECTION_HEADING_REGEX.match(valid_heading_4) is not None

    # Numbered exercise items MUST NOT match as section headings
    invalid_exercise_1 = "1. Kelompok riset sistem tata surya a. Kelompok ini akan melakukan riset..."
    invalid_exercise_2 = "4. Bayangkan lingkungan tempat tinggalmu mengalami perubahan iklim, seperti kemarau..."
    invalid_exercise_3 = "3. Buat diagram batang atau garis dari tabel frekuensi..."
    invalid_exercise_4 = "5. Setelah dua menit, keluarkan semua bahan makanan dari kantong plastik..."

    assert SECTION_HEADING_REGEX.match(invalid_exercise_1) is None
    assert SECTION_HEADING_REGEX.match(invalid_exercise_2) is None
    assert SECTION_HEADING_REGEX.match(invalid_exercise_3) is None
    assert SECTION_HEADING_REGEX.match(invalid_exercise_4) is None


def test_rubric_and_reflection_filter():
    """is_exercise_or_instruction_chunk must detect rubric score tables and end-of-chapter reflection boxes."""
    rubric_text = "Skor maksimal 100 Berikut tabel penilaian untuk kamu salin di buku tugas! Nama Kriteria Skor Paraf guru..."
    reflection_text = "Selamat! Kalian sudah menyelesaikan bab kelima di buku ini. Apa saja yang sudah kalian pelajari di Bab 5 ini? Pengalaman belajar favorit saya..."
    concept_text = "Energi surya merupakan salah satu sumber energi terbarukan yang memanfaatkan radiasi sinar matahari untuk diubah menjadi energi listrik melalui panel surya."

    assert is_exercise_or_instruction_chunk(rubric_text) is True
    assert is_exercise_or_instruction_chunk(reflection_text) is True
    assert is_exercise_or_instruction_chunk(concept_text) is False


def test_fixed_chunker_inherits_chapter_and_heading():
    """FixedChunker should correctly inherit chapter and clean headings across pages."""
    pages = [
        PageContent(
            page_number=121,
            text="Topik A: Mengapa Kita Memerlukan Energi\nSetiap aktivitas manusia membutuhkan energi untuk bergerak dan bernapas. Energi diperoleh dari makanan dan sumber daya alam sekitar kita.",
            chapter="Bab 5: Energi untuk Masa Depan"
        ),
        PageContent(
            page_number=122,
            text="Panel surya adalah alat untuk mengubah energi matahari menjadi energi listrik yang ramah lingkungan dan tidak menghasilkan polusi udara.",
            chapter="Bab 5: Energi untuk Masa Depan"
        ),
    ]

    chunker = FixedChunker(chunk_size=1000, chunk_overlap=150)
    chunks = chunker.chunk_pages(pages)

    assert len(chunks) >= 1
    assert chunks[0].chapter == "Bab 5: Energi untuk Masa Depan"
    assert chunks[0].section_heading == "Topik A: Mengapa Kita Memerlukan Energi"
    assert chunks[0].page_number in (121, 122)
