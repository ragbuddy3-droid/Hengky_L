"""PDF text extraction module with page-aware front-matter and back-matter filtering."""

import logging
import re
import time
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
]


def normalize_text_fonts(text: str) -> str:
    """Normalize duplicated font characters commonly produced by PDF extractors (e.g. KKaattaa -> Kata)."""
    def fix_word(w: str) -> str:
        if len(w) >= 4 and len(w) % 2 == 0 and all(w[i] == w[i + 1] for i in range(0, len(w) - 1, 2)):
            return w[::2]
        return w
    words = text.split()
    fixed_words = [fix_word(w) for w in words]
    return " ".join(fixed_words)


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


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract page text using pdfplumber (primary) with pypdf fallback, skipping front and back matter."""
    pages_data = []

    try:
        logger.info("Using pdfplumber (primary extractor) for: %s", file_path.name)
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            main_started = False

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

                pages_data.append(extracted)

            logger.info("Extracted %d main content pages out of %d total pages", len(pages_data), page_count)

    except Exception as e:
        logger.warning("pdfplumber failed (%s), falling back to pypdf", e)
        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        main_started = False

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

            pages_data.append(extracted)

    full_text = "\n".join(pages_data)
    logger.info("Extracted main content text length: %s chars", f"{len(full_text):,}")
    return full_text


def clean_text(text: str) -> str:
    """Remove noise lines, headers, footers, page numbers, and excessive whitespace."""
    original_len = len(text)
    logger.info("Cleaning text (input length: %s chars)", f"{original_len:,}")

    lines = text.split('\n')
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
    result = re.sub(r' {2,}', ' ', result)
    result = result.strip()

    cleaned_len = len(result)
    removed_pct = ((original_len - cleaned_len) / original_len * 100) if original_len > 0 else 0
    logger.info("Clean text length: %s chars (removed %.1f%%)", f"{cleaned_len:,}", removed_pct)
    return result


def process_pdf(file_path: Path) -> str:
    """Orchestrate extraction + front-matter filtering + cleaning."""
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info("=" * 50)
    logger.info("Starting PDF processing: '%s' (%.2fMB)", file_path.name, file_size_mb)

    start_time = time.time()
    raw_text = extract_text_from_pdf(file_path)
    clean = clean_text(raw_text)
    elapsed = time.time() - start_time

    logger.info("PDF extraction & cleaning complete in %.2fs", elapsed)
    logger.info("=" * 50)
    return clean
