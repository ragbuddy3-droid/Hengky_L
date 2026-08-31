"""Shared structural and semantic text taggers and chapter/heading extractors."""

import re

ROMAN_MAP = {
    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
    'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
    'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
}

# Strict chapter anchor regex: matches "Bab 1: Judul", "Bab 1 | Judul", or "Bab 1"
CHAPTER_START_REGEX = re.compile(
    r'^\s*(?:BAB|UNIT|TEMA|MODUL|CHAPTER|PEMBELAJARAN)\s+([0-9IVXLCDM]+)(?:[\s:\.\-–—\|]+(.*))?$',
    re.IGNORECASE,
)

# Section heading patterns: strictly matches major section headings like "Topik A: ...", "Bagian B: ...", "A. Organ Pernapasan"
# Excludes numbered exercise items (e.g. "1. ...", "2. ...") and long sentences
SECTION_HEADING_REGEX = re.compile(
    r'^\s*(?:Topik\s+[A-Z]|Bagian\s+[A-Z]|[A-Z]\.)[\s:\.\-–—]+([^\n\r\.\,\;\:\!\?]{3,60})$',
    re.IGNORECASE,
)


def classify_chunk_category(text: str) -> str:
    """
    Tag chunk into structural & substantive content categories without dropping material.
    Returns: 'materi_pokok' | 'uraian_materi' | 'studi_kasus' | 'aktivitas_diskusi' | 'rangkuman'
    """
    lower = text.lower()

    if any(k in lower for k in ["tabel penilaian", "skor maksimal", "kriteria skor", "rubrik penilaian", "lembar penilaian"]):
        return "aktivitas_diskusi"

    if any(k in lower for k in ["rangkuman", "kesimpulan", "ringkasan materi", "peta konsep"]):
        return "rangkuman"

    if any(k in lower for k in ["studi kasus", "contoh kasus", "tahukah kamu", "fakta menarik", "pernahkah kamu"]):
        return "studi_kasus"

    if any(k in lower for k in ["ayo mencoba", "mari berdiskusi", "kegiatan penyelidikan", "langkah kerja", "tugas kelompok", "ayo, menyelidiki", "ayo, mengamati", "siap-siap belajar"]):
        return "aktivitas_diskusi"

    # Core concept markers (scientific definitions, processes, organs, systems)
    konsep_patterns = [
        r"\b(adalah|merupakan|yaitu|artinya|didefinisikan sebagai|terdiri atas|fungsi dari|organ|sistem|proses|enzim|energi)\b"
    ]
    if any(re.search(pat, lower) for pat in konsep_patterns):
        return "materi_pokok"

    return "uraian_materi"


def extract_chapter_and_heading(
    text: str,
    prev_chapter: str | None,
    prev_heading: str | None,
) -> tuple[str | None, str | None]:
    """
    Extract or inherit structured chapter and section heading from text lines.
    Rejects colloquial mentions, numbered exercises, and lengthy instruction sentences.
    """
    chapter = prev_chapter
    heading = prev_heading

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    for line in lines[:5]:
        # Exclude table of contents dots e.g. "Bab 1 .... 12"
        if "..." in line or "...." in line:
            continue

        # Check for strict Chapter Header
        chap_match = CHAPTER_START_REGEX.match(line)
        if chap_match:
            raw_num = chap_match.group(1).upper()
            norm_num = ROMAN_MAP.get(raw_num, raw_num)
            title = (chap_match.group(2) or "").strip(" :.-–—|")
            # Strip trailing page numbers if any
            title = re.sub(r'\s+\d+$', '', title).strip()
            if title and len(title) > 2:
                chapter = f"Bab {norm_num}: {title}"
            else:
                chapter = f"Bab {norm_num}"
            continue

        # Check for Section Heading (e.g. "Topik A: Cara Kerja Sistem Pencernaan", "A. Organ Pernapasan")
        sec_match = SECTION_HEADING_REGEX.match(line)
        if sec_match:
            h_candidate = line.strip(" :.-–—|")
            # Exclude exercise imperative prompts
            if not any(kw in h_candidate.lower() for kw in ["jawablah", "bacalah", "buatlah", "amati", "salinlah", "diskusikan", "gambar", "tabel", "sumber"]):
                if len(h_candidate) <= 60:
                    heading = h_candidate
                    continue

        # Generic title line heuristic for standalone title headers (short, title-cased, no sentence punctuation)
        if (
            2 <= len(line.split()) <= 6
            and len(line) <= 45
            and not line.endswith((".", ":", "?", "!", ";", ","))
            and not re.search(r'^(gambar|tabel|sumber|kementerian|halaman|skor|nama|kriteria|no\.)\b', line, re.IGNORECASE)
            and (line.isupper() or line.istitle())
            and not any(stop in line.lower() for stop in ["halaman", "kementerian", "republik indonesia", "guru", "siswa", "buku tugas"])
        ):
            heading = line.strip()

    return chapter, heading
