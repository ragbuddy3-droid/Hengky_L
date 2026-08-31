"""PDF text extraction module with page-aware front-matter and back-matter filtering."""

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

logger = logging.getLogger(__name__)

ROMAN_REGEX = re.compile(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv)$', re.IGNORECASE)

FRONT_MATTER_TITLES = [
    'kata pengantar', 'prakata', 'daftar isi', 'daftar gambar', 'daftar tabel',
    'hak cipta', 'sanksi pelanggaran', 'petunjuk penggunaan', 'profil pelaku perbukuan',
    'profil penulis', 'profil penelaah', 'profil editor', 'profil ilustrator',
    'profil desainer', 'tentang buku ini', 'ada apa di buku ini', 'sambutan',
    'buku panduan guru', 'buku siswa', 'pengenalan karakter', 'lihat di lingkungan sekitar'
]

BACK_MATTER_TITLES = [
    'glosarium', 'daftar pustaka', 'profil pelaku perbukuan',
    'profil penulis', 'profil penelaah', 'profil editor', 'profil ilustrator',
    'profil desainer', 'indeks'
]

NOISE_PATTERNS = [
    r'^Sumber:\s*.*$',
    r'^Gambar\s*\d+(\.\d+)?\s+.*$',
    r'^\d+\s+Ilmu Pengetahuan.*$',
    r'^\d+\s*$',
    r'(?i)^Bab\s+\d+\s*\|.*$',
    r'(?i)^Hak Cipta.*$',
    r'(?i)^Kementerian Pendidikan.*$',
    r'(?i)^ISBN\b.*$',
    r'(?i)^Berikut tabel penilaian.*$',
    r'(?i)^Skor maksimal\s+\d+.*$',
    r'(?i)^Nama Kriteria Skor Paraf guru.*$',
    r'(?i)^Aspek yang Dinilai Kriteria Skor.*$',
]

CHAPTER_RUNNING_REGEX = re.compile(
    r'(?i)\b(?:Bab|Unit|Tema|Modul)\s+([0-9IVXLCDM]+)\s*\|\s*([^\n\r\|0-9\.\,\:\;\!\?]{3,80})',
    re.IGNORECASE
)
CHAPTER_OPENER_REGEX = re.compile(
    r'(?i)^\s*(?:BAB|UNIT|TEMA|MODUL|CHAPTER|PEMBELAJARAN)\s+([0-9IVXLCDM]+)(?:[\s:\.\-–—]+([^\n\r\.\,\:\;\!\?]{3,80}))?$',
    re.MULTILINE
)


def extract_chapter_from_raw_page(raw_text: str) -> str | None:
    """Extract chapter identifier from raw page text or running headers."""
    if not raw_text:
        return None
    norm = normalize_text_fonts(raw_text)

    # 1. Check running header pattern: e.g. "Bab 5 | Energi untuk Masa Depan 139"
    m_running = CHAPTER_RUNNING_REGEX.search(norm)
    if m_running:
        num = m_running.group(1).upper()
        title = m_running.group(2).strip()
        title = re.sub(r'\s+\d+$', '', title).strip()
        return f"Bab {num}: {title}" if title else f"Bab {num}"

    # 2. Check chapter title lines: e.g. "Bab 1: Makanan Bergizi"
    for line in norm.split('\n')[:8]:
        line_clean = line.strip()
        m_open = CHAPTER_OPENER_REGEX.match(line_clean)
        if m_open and "..." not in line_clean:
            num = m_open.group(1).upper()
            title = (m_open.group(2) or "").strip()
            return f"Bab {num}: {title}" if title else f"Bab {num}"

    return None


@dataclass
class PageContent:
    """Represents extracted text from a specific physical PDF page."""
    page_number: int  # 1-indexed
    text: str
    chapter: str | None = None


def normalize_text_fonts(text: str) -> str:
    """Normalize duplicated font characters and CID artifacts while strictly preserving line breaks."""
    if not text:
        return ""

    # 1. Fix common CID ligature encoding issues from Kemdikbud PDFs
    text = text.replace("(cid:1652)", "fi")
    text = text.replace("(cid:1651)", "fl")
    text = text.replace("(cid:1650)", "ff")
    text = re.sub(r'\(cid:\d+\)', '', text)

    # 2. Fix duplicated character sequences (e.g. KKaattaa -> Kata, EEnneerrggii -> Energi)
    def fix_word(w: str) -> str:
        if len(w) >= 4 and len(w) % 2 == 0 and all(w[i] == w[i + 1] for i in range(0, len(w) - 1, 2)):
            return w[::2]
        return w

    # Preserve line structure
    lines = text.split('\n')
    fixed_lines = []
    for line in lines:
        words = line.split()
        if not words:
            fixed_lines.append("")
            continue
        fixed_words = [fix_word(w) for w in words]
        fixed_lines.append(" ".join(fixed_words))
    return "\n".join(fixed_lines)


def is_roman_numeral(val: str) -> bool:
    """Check if string is a roman numeral."""
    return bool(ROMAN_REGEX.match(val.strip().lower()))


def is_front_matter_page(raw_text: str, lines: list[str], page_idx: int) -> bool:
    """Determine if a page belongs to front matter."""
    text_norm = normalize_text_fonts(raw_text).lower()

    # 1. Header or title match in top 5 lines
    for line in lines[:5]:
        line_clean = normalize_text_fonts(line.strip().lower())
        if any(fm in line_clean for fm in FRONT_MATTER_TITLES):
            return True

    # 2. Check if footer contains Roman page number
    for line in lines[-2:]:
        for token in line.split():
            clean_tok = token.strip('.,()|[]')
            if is_roman_numeral(clean_tok):
                return True

    # 3. Check for copyright / Ministry info on very early pages
    return bool(
        page_idx < 4
        and any(kw in text_norm for kw in ['hak cipta', 'kementerian pendidikan', 'isbn', 'sanksi pelanggaran'])
    )


def extract_pages_from_pdf(file_path: Path) -> list[PageContent]:
    """Extract pages as a list of PageContent objects with front/back matter filtering and chapter tracking."""
    pages_data: list[PageContent] = []

    try:
        logger.info("Using pdfplumber (primary extractor) for: %s", file_path.name)
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            main_started = False
            current_chapter: str | None = None

            for i, page in enumerate(pdf.pages):
                extracted = page.extract_text() or ""
                lines = [line_str.strip() for line_str in extracted.split('\n') if line_str.strip()]
                if not lines:
                    continue

                # Check for chapter title page start (e.g. Bab 1 / Pembelajaran 1 / Unit 1)
                is_bab1_start = False
                page_norm = normalize_text_fonts(extracted)
                if re.search(r'\b(Bab|Chapter|Unit|Pembelajaran|Modul)\b', page_norm, re.IGNORECASE):
                    for line_str in lines[:10]:
                        l_norm = normalize_text_fonts(line_str).strip()
                        if '...' in l_norm or '....' in l_norm:
                            continue
                        if re.search(r'^\s*(Bab|Chapter|Unit|Pembelajaran|Modul)?\s*(1|I)\b', l_norm, re.IGNORECASE) or l_norm in ['1', 'I']:
                            is_bab1_start = True
                            break

                # Front matter exclusion
                if not main_started:
                    if is_bab1_start or (not is_front_matter_page(extracted, lines, i) and i >= 5):
                        main_started = True
                        logger.info("Main content start detected at Page %d", i + 1)
                    else:
                        logger.debug("Skipping front-matter page %d", i + 1)
                        continue

                # Back matter exclusion (only near tail of document)
                is_back_matter = False
                for line in lines[:3]:
                    line_norm = normalize_text_fonts(line.strip().lower())
                    if any(bm in line_norm for bm in BACK_MATTER_TITLES):
                        is_back_matter = True
                        break
                if is_back_matter and i > page_count * 0.8:
                    logger.info("Back-matter reached at Page %d, stopping page extraction.", i + 1)
                    break

                # Track active chapter across pages
                detected_ch = extract_chapter_from_raw_page(extracted)
                if detected_ch:
                    current_chapter = detected_ch

                cleaned_page_text = clean_text(extracted)
                if cleaned_page_text:
                    pages_data.append(PageContent(page_number=i + 1, text=cleaned_page_text, chapter=current_chapter))

            logger.info("Extracted %d main content pages out of %d total pages", len(pages_data), page_count)

    except Exception as e:
        logger.warning("pdfplumber failed (%s), falling back to pypdf", e)
        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        main_started = False
        current_chapter = None

        for i, page in enumerate(reader.pages):
            extracted = page.extract_text() or ""
            lines = [line_str.strip() for line_str in extracted.split('\n') if line_str.strip()]
            if not lines:
                continue

            is_bab1_start = False
            for line in lines[:5]:
                line_norm = normalize_text_fonts(line)
                if re.match(r'^(Bab|Chapter|Unit|Pembelajaran|Modul)\s+(1|I)\b', line_norm, re.IGNORECASE) and '...' not in line_norm:
                    is_bab1_start = True
                    break

            if not main_started:
                if is_bab1_start or (not is_front_matter_page(extracted, lines, i) and i >= 5):
                    main_started = True
                else:
                    continue

            # Back matter exclusion (only near tail of document)
            is_back_matter = False
            for line in lines[:3]:
                line_norm = normalize_text_fonts(line.strip().lower())
                if any(bm in line_norm for bm in BACK_MATTER_TITLES):
                    is_back_matter = True
                    break
            if is_back_matter and i > page_count * 0.8:
                logger.info("Back-matter reached at Page %d (pypdf fallback), stopping.", i + 1)
                break

            detected_ch = extract_chapter_from_raw_page(extracted)
            if detected_ch:
                current_chapter = detected_ch

            cleaned_page_text = clean_text(extracted)
            if cleaned_page_text:
                pages_data.append(PageContent(page_number=i + 1, text=cleaned_page_text, chapter=current_chapter))

    return pages_data


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract full main content text from PDF."""
    pages = extract_pages_from_pdf(file_path)
    full_text = "\n\n".join(p.text for p in pages)
    logger.info("Extracted main content text length: %s chars across %d pages", f"{len(full_text):,}", len(pages))
    return full_text


def clean_text(text: str) -> str:
    """Remove noise lines, headers, footers, page numbers, and excessive whitespace."""
    if not text:
        return ""
    text_norm = normalize_text_fonts(text)
    lines = text_norm.split('\n')
    cleaned_lines = []

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        is_noise = False
        for pat in NOISE_PATTERNS:
            if re.match(pat, line_str, re.IGNORECASE):
                is_noise = True
                break

        if not is_noise:
            cleaned_lines.append(line_str)

    result = "\n".join(cleaned_lines)

    # Normalize whitespace
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r'[ \t]{2,}', ' ', result)
    return result.strip()


def process_pdf(file_path: Path) -> str:
    """Orchestrate extraction + front-matter filtering + cleaning."""
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info("=" * 50)
    logger.info("Starting PDF processing: '%s' (%.2fMB)", file_path.name, file_size_mb)

    start_time = time.time()
    raw_text = extract_text_from_pdf(file_path)
    elapsed = time.time() - start_time

    logger.info("PDF extraction & cleaning complete in %.2fs", elapsed)
    logger.info("=" * 50)
    return raw_text


def process_pdf_pages(file_path: Path) -> list[PageContent]:
    """Process PDF and return list of cleaned PageContent objects with page numbers."""
    return extract_pages_from_pdf(file_path)
