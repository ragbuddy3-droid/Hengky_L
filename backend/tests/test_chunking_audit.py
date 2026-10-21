"""Comprehensive unit and regression tests for Chapter Extraction, Section Heading Scoping, Rubric Filtering, and Context Traceability."""

from app.services.ingestion.chunkers.classifiers import (
    SECTION_HEADING_REGEX,
)
from app.services.ingestion.chunkers.fixed_chunker import FixedChunker
from app.services.ingestion.extractor import (
    ChapterInfo,
    PageContent,
    build_pages,
    clean_text,
    extract_chapter_from_raw_page,
    is_valid_toc_title,
    match_running_header,
    resolve_chapter_titles,
)
from app.services.retrieval.hybrid_search import is_exercise_or_instruction_chunk
from app.services.validation.quality_checks import find_book_navigation_issue, validate_answer_quality


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


def _page(*lines: str) -> str:
    return "\n".join(lines)


def test_prose_mention_of_earlier_chapter_does_not_move_chapter_back():
    """'Ingat, di Bab 2 kamu sudah belajar ...' on a Bab 6 page must stay in Bab 6."""
    filler = "Energi membuat benda dapat bergerak dan berubah bentuk setiap hari."
    raw_pages = [(i, _page("KATA PENGANTAR", "Buku ini disusun untuk siswa.", "iii")) for i in range(1, 5)]
    raw_pages += [
        (5, _page("KEMENTERIAN PENDIDIKAN", "Bab", "1", "Keajaiban Tubuhku", filler)),
        (6, _page(filler, "Bab 1 | Keajaiban Tubuhku 2")),
        (7, _page("Bab", "2", "Dahulu, Kini, dan Nanti", filler)),
        (8, _page(filler, "Bab 2 | Dahulu, Kini, dan Nanti 4")),
        (9, _page("Bab", "3", "Energi, sang Pemberi Kekuatan", filler)),
        (10, _page("Perhatikan cara mereka bekerja.", "Ingat, di Bab 2 kamu sudah belajar", "tentang perubahan.", filler)),
        (11, _page(filler, "Bab 3 | Energi, sang Pemberi Kekuatan 7")),
    ]
    pages = build_pages(raw_pages)
    chapters = {p.page_number: p.chapter for p in pages}
    assert chapters[10] == "Bab 3: Energi, sang Pemberi Kekuatan"
    assert chapters[8] == "Bab 2: Dahulu, Kini, dan Nanti"


def test_running_header_keeps_full_title_with_comma_and_exclamation():
    assert match_running_header("Bab 1 | Ayo, Gerakkan Badanmu! 3") == (1, "Ayo, Gerakkan Badanmu!")
    assert match_running_header("Bab 8 Menjadi Pahlawan Lingkungan 8") == (8, "Menjadi Pahlawan Lingkungan")
    assert match_running_header("Ingat, di Bab 2 kamu sudah belajar") is None


def test_running_header_votes_beat_mangled_toc_titles():
    footer = "Bab 2 Mengamalkan Pancasila untuk Kebahagiaan Bersama 27"
    pages = [_page("Isi halaman.", footer)] * 3
    toc = [ChapterInfo(number=2, title="Kata Pengantar iii Mengamalkan Pancasila Prakata vii untuk Kebahagiaan")]
    assert resolve_chapter_titles(pages, toc) == {2: "Mengamalkan Pancasila untuk Kebahagiaan Bersama"}
    assert not is_valid_toc_title("Budaya dan Agama 1. Indahnya Provinsiku Bagian dari Keberagaman")
    assert is_valid_toc_title("Berpikir Cerdas, Bergerak Taktis")


def test_clean_text_drops_running_footers_links_and_barcode_instructions():
    raw = _page(
        "Musyawarah adalah cara mengambil keputusan bersama.",
        "Jika kalian tidak mengalami kesulitan, bu-",
        "kalah tautan berikut. https://buku.kemdikbud.",
        "go.id/s/bukubacaan",
        "Scan barcode di samping",
        "untuk membaca narasi",
        "“Bencana di Pulau Seberang”.",
        "Hasil musyawarah harus diterima dengan lapang dada.",
        "Bab 4 Belajar Bermusyawarah 91",
        "112 Pendidikan Pancasila untuk SD/MI Kelas VI",
    )
    cleaned = clean_text(raw)
    assert "Musyawarah adalah cara mengambil keputusan bersama." in cleaned
    assert "Hasil musyawarah harus diterima dengan lapang dada." in cleaned
    for leftover in ("barcode", "tautan", "http", "kemdikbud", "Bab 4 Belajar", "SD/MI"):
        assert leftover not in cleaned


def test_book_navigation_question_is_rejected():
    question = {
        "question": "Bagaimana cara kamu membaca narasi 'Bencana di Pulau Seberang'?",
        "answer": "Kamu perlu memindai barcode yang ada di samping teks untuk membaca narasi tersebut.",
        "question_type": "esai_pendek",
    }
    issues = validate_answer_quality(question)
    assert any("cara memakai buku" in issue for issue in issues)
    assert find_book_navigation_issue("Bagaimana cara membaca peta dengan benar?") is None
