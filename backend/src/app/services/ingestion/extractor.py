"""PDF text extraction module with page-aware front-matter and back-matter filtering."""

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

logger = logging.getLogger(__name__)

ROMAN_REGEX = re.compile(
    r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$',
    re.IGNORECASE
)

ROMAN_MAP = {
    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
    'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
    'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
    'XVI': '16', 'XVII': '17', 'XVIII': '18', 'XIX': '19', 'XX': '20',
}

FRONT_MATTER_TITLES = [
    'kata pengantar', 'prakata', 'daftar isi', 'daftar gambar', 'daftar tabel',
    'daftar kredit gambar', 'daftar sumber gambar',
    'hak cipta', 'sanksi pelanggaran', 'penafian', 'petunjuk penggunaan',
    'profil pelaku perbukuan', 'tentang buku ini', 'ada apa di buku ini',
    'sambutan', 'buku panduan guru', 'buku panduan siswa', 'buku siswa',
    'pengenalan karakter', 'perkenalan tokoh', 'pengenalan tokoh',
    'penjelasan fitur buku', 'panduan penggunaan buku', 'pedoman penggunaan buku'
]

BACK_MATTER_TITLES = [
    'glosarium', 'daftar pustaka', 'profil pelaku perbukuan',
    'profil penulis', 'profil penelaah', 'profil editor', 'profil ilustrator',
    'profil desainer', 'profil editor visual', 'profil perbukuan',
    'biografi pelaku perbukuan', 'pelaku perbukuan', 'indeks',
    'lampiran', 'lampiran lembar kerja', 'lampiranlembarkerja'
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
    r'(?i)\b(?:Bab|Unit|Tema|Modul|Pelajaran)\s+([0-9IVXLCDM]+)\s*(?:\||:|\s)\s*([^\n\r\|0-9\.\,\:\;\!\?]{3,80})',
    re.IGNORECASE
)
CHAPTER_OPENER_REGEX = re.compile(
    r'(?i)^\s*(?:BAB|UNIT|TEMA|MODUL|CHAPTER|PEMBELAJARAN)\s+([0-9IVXLCDM]+)(?:[\s:\.\-–—\|]+([^\n\r\.\,\:\;\!\?]{3,80}))?$',
    re.MULTILINE
)


@dataclass
class ChapterInfo:
    """Structured chapter metadata."""
    number: str
    title: str
    full_label: str


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
    text = text.replace("(cid:2146)", "fi")
    text = text.replace("(cid:444)", "fi")
    text = re.sub(r'\(cid:\d+\)', '', text)

    # 2. Fix duplicated character sequences (e.g. 11 -> 1, BBaabb -> Bab, AA.. -> A.)
    def fix_word(w: str) -> str:
        if len(w) >= 2 and len(w) % 2 == 0 and all(w[i] == w[i + 1] for i in range(0, len(w) - 1, 2)):
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
        fixed_line = " ".join(fixed_words)
        fixed_line = re.sub(r'\b([A-Za-z0-9])\s+\1\b', r'\1', fixed_line)
        fixed_lines.append(fixed_line)
    return "\n".join(fixed_lines)


def is_roman_numeral(val: str) -> bool:
    """Check if string is a valid Roman numeral (i to xx)."""
    return bool(ROMAN_REGEX.match(val.strip().lower()))


def parse_toc_from_pages(raw_pages: list[str]) -> list[ChapterInfo]:
    """
    Parse Table of Contents (Daftar Isi) from the early pages of the textbook.
    Returns structured list of ChapterInfo objects.
    """
    chapters: list[ChapterInfo] = []
    in_toc = False
    toc_lines: list[str] = []

    for text in raw_pages[:15]:
        norm = normalize_text_fonts(text)
        lines = [l.strip() for l in norm.split('\n') if l.strip()]

        is_toc_page = any(
            re.search(r'\bdaftar\s+isi\b', l, re.IGNORECASE)
            for l in lines[:5]
        )

        if is_toc_page:
            in_toc = True
            toc_lines.extend(lines)
        elif in_toc:
            has_toc_entries = any(
                re.search(r'\b(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s+\d+', l, re.IGNORECASE)
                or re.search(r'\.{3,}\s*\d+', l)
                or re.match(r'^[A-Z]\.\s+', l)
                for l in lines[:8]
            )
            is_other_fm = any(
                any(fmt in l.lower() for fmt in ['daftar gambar', 'daftar tabel', 'petunjuk penggunaan', 'ada apa di buku', 'penjelasan fitur', 'pengenalan'])
                for l in lines[:5]
            )
            if has_toc_entries and not is_other_fm:
                toc_lines.extend(lines)
            else:
                in_toc = False

    combined_toc = "\n".join(toc_lines)
    chap_pattern = re.compile(
        r'(?i)\b(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s+([0-9IVXLCDM]+)[\s:\.\-–—\|]*(.*?)(?=\n\s*(?:Bab|Unit|Tema|Pelajaran|Pembelajaran|\b[A-Z]\.|\bGlosarium|\bDaftar|\bProfil|\bIndeks|\bLampiran|\Z))',
        re.DOTALL
    )

    for m in chap_pattern.finditer(combined_toc):
        raw_num = m.group(1).upper()
        if raw_num in ['DI', 'DAN', 'KE', 'DARI']:
            continue
        norm_num = ROMAN_MAP.get(raw_num, raw_num)
        norm_num = str(int(norm_num)) if norm_num.isdigit() else norm_num
        raw_title = m.group(2).strip()

        lines = [l.strip() for l in raw_title.split('\n') if l.strip()]
        if not lines:
            continue

        title_parts = []
        for l in lines:
            if re.match(r'^[A-Z]\.\s+', l) or re.match(r'^(?:Topik|Bagian)\s+[A-Z]', l, re.IGNORECASE):
                break
            cleaned = re.sub(r'\.{2,}\s*\d*', '', l)
            cleaned = re.sub(r'\s+\d+$', '', cleaned)
            cleaned = re.sub(r'^\d+\s+', '', cleaned)
            cleaned = cleaned.strip(" :.-–—|")
            if cleaned and not re.match(r'^\d+$', cleaned) and cleaned.lower() not in ['hal', 'halaman']:
                title_parts.append(cleaned)

        title = " ".join(title_parts).strip()
        title = re.sub(r'\s+', ' ', title)

        if title:
            full_label = f"Bab {norm_num}: {title}"
        else:
            full_label = f"Bab {norm_num}"

        if not any(c.number == norm_num for c in chapters):
            chapters.append(ChapterInfo(number=norm_num, title=title, full_label=full_label))

    return chapters


def detect_chapter_opener(page_norm: str, toc_map: dict[str, ChapterInfo]) -> ChapterInfo | None:
    """Detect if a page is a chapter opening page using multiple signals + TOC mapping."""
    lines = [l.strip() for l in page_norm.split('\n') if l.strip()]
    if not lines:
        return None

    # 1. Look for explicit "Bab <num>" in top lines
    for idx, line in enumerate(lines[:10]):
        # Match single-line "Bab 1", "Bab 1: Judul", "Bab 1 | Judul"
        m = re.search(r'\b(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s+([0-9IVXLCDM]+)(?:[\s:\.\-–—\|]+(.*))?$', line, re.IGNORECASE)
        if m and "..." not in line:
            num = m.group(1).upper()
            if num in ['DI', 'DAN', 'KE', 'DARI']:
                continue
            num = ROMAN_MAP.get(num, num)
            num = str(int(num)) if num.isdigit() else num
            inline_title = (m.group(2) or "").strip(" :.-–—|")
            inline_title = re.sub(r'\s+\d+$', '', inline_title).strip()

            if num in toc_map:
                return toc_map[num]
            elif inline_title and len(inline_title) > 2:
                return ChapterInfo(number=num, title=inline_title, full_label=f"Bab {num}: {inline_title}")
            else:
                return ChapterInfo(number=num, title="", full_label=f"Bab {num}")

        # Match multiline "Bab" followed by "<num>" on next line
        if re.match(r'^(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)$', line, re.IGNORECASE) and idx + 1 < len(lines):
            next_line = lines[idx + 1].strip()
            num_match = re.match(r'^([0-9IVXLCDM]+)$', next_line, re.IGNORECASE)
            if num_match:
                num = num_match.group(1).upper()
                if num in ['DI', 'DAN', 'KE', 'DARI']:
                    continue
                num = ROMAN_MAP.get(num, num)
                num = str(int(num)) if num.isdigit() else num
                if num in toc_map:
                    return toc_map[num]
                title_cand = lines[idx + 2].strip() if idx + 2 < len(lines) else ""
                if title_cand and len(title_cand) < 60 and not re.match(r'^\d+$', title_cand):
                    return ChapterInfo(number=num, title=title_cand, full_label=f"Bab {num}: {title_cand}")
                return ChapterInfo(number=num, title="", full_label=f"Bab {num}")

    # 2. Look for Kemdikbud chapter cover patterns where "Bab" and "<num>" appear in header block
    for idx, line in enumerate(lines[:6]):
        if re.search(r'\bBab\b', line, re.IGNORECASE):
            for s_idx, sub_line in enumerate(lines[idx:idx+6]):
                m_num = re.match(r'^\s*([0-9]{1,2}|[IVXLCDM]+)\s*$', sub_line)
                if m_num:
                    num = m_num.group(1).upper()
                    if num not in ['DI', 'DAN', 'KE', 'DARI']:
                        num = ROMAN_MAP.get(num, num)
                        num = str(int(num)) if num.isdigit() else num
                        if num in toc_map:
                            return toc_map[num]
                        title_lines = []
                        for t_line in lines[idx + s_idx + 1: idx + s_idx + 6]:
                            if any(k in t_line.lower() for k in ['penulis', 'isbn', 'kementerian', 'republik', 'pendidikan']):
                                continue
                            if any(t_line.lower().startswith(q) for q in ['bagaimana', 'mengapa', 'apakah', 'pernahkah', 'tahukah', 'siapakah', 'kapan', 'di mana', 'mari', 'pada bab']):
                                break
                            if t_line.endswith(('?', '!', '.', ':', ';')):
                                cleaned_t = t_line.strip(" :.-–—|!?")
                                if cleaned_t and len(cleaned_t) < 50:
                                    title_lines.append(cleaned_t)
                                break
                            if len(t_line) < 50:
                                title_lines.append(t_line.strip(" :.-–—|!?"))
                        title = " ".join(title_lines).strip()
                        if title:
                            return ChapterInfo(number=num, title=title, full_label=f"Bab {num}: {title}")
                        return ChapterInfo(number=num, title="", full_label=f"Bab {num}")

    # 3. Match known TOC chapter titles directly if they appear prominently in top lines
    for num, ch_info in toc_map.items():
        if ch_info.title and len(ch_info.title) > 4:
            for line in lines[:8]:
                if ch_info.title.lower() in line.lower() and len(line) < len(ch_info.title) + 15:
                    return ch_info

    return None


def detect_chapter_running_header(page_norm: str, toc_map: dict[str, ChapterInfo]) -> ChapterInfo | None:
    """Extract chapter from running header/footer, safely filtering out false positives."""
    lines = [l.strip() for l in page_norm.split('\n') if l.strip()]
    if not lines:
        return None

    candidate_lines = lines[:2] + lines[-2:]
    for line in candidate_lines:
        m = CHAPTER_RUNNING_REGEX.search(line)
        if m and "..." not in line:
            num = m.group(1).upper()
            if num in ['DI', 'DAN', 'KE', 'DARI', 'PADA']:
                continue
            num = ROMAN_MAP.get(num, num)
            num = str(int(num)) if num.isdigit() else num

            raw_title = m.group(2).strip(" :.-–—|")
            raw_title = re.sub(r'\s+\d+$', '', raw_title).strip()

            if num in toc_map:
                return toc_map[num]
            elif raw_title and len(raw_title) > 2:
                return ChapterInfo(number=num, title=raw_title, full_label=f"Bab {num}: {raw_title}")
            else:
                return ChapterInfo(number=num, title="", full_label=f"Bab {num}")

    return None


def is_front_matter_page(raw_text: str, lines: list[str], page_idx: int) -> bool:
    """Determine if a page belongs to front matter."""
    text_norm = normalize_text_fonts(raw_text).lower()

    # 1. Header or title match in top 8 lines
    for line in lines[:8]:
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
    if page_idx < 6 and any(kw in text_norm for kw in ['hak cipta', 'kementerian pendidikan', 'isbn', 'sanksi pelanggaran', 'penafian:']):
        return True

    # 4. Check for icon guides / feature explanation pages in first 20 pages
    if page_idx < 20:
        icon_guide_markers = [
            'ada apa di buku ini', 'petunjuk penggunaan buku', 'penjelasan fitur buku',
            'tujuan pembelajaran', 'kata kunci', 'siap-siap belajar', 'mari mengamati',
            'mari bernyanyi', 'mari berkarya', 'mari berlatih', 'uji kemampuanku',
            'pindai aku', 'pengenalan karakter', 'perkenalan tokoh', 'apersepsi'
        ]
        marker_count = sum(1 for marker in icon_guide_markers if marker in text_norm)
        if marker_count >= 3:
            return True

    return False


def extract_chapter_from_raw_page(raw_text: str) -> str | None:
    """Extract chapter identifier from raw page text (compatibility helper)."""
    if not raw_text:
        return None
    norm = normalize_text_fonts(raw_text)

    m_running = CHAPTER_RUNNING_REGEX.search(norm)
    if m_running:
        num = m_running.group(1).upper()
        if num not in ['DI', 'DAN', 'KE', 'DARI', 'PADA']:
            num = ROMAN_MAP.get(num, num)
            num = str(int(num)) if num.isdigit() else num
            title = m_running.group(2).strip(" :.-–—|")
            title = re.sub(r'\s+\d+$', '', title).strip()
            return f"Bab {num}: {title}" if title else f"Bab {num}"

    for line in norm.split('\n')[:8]:
        line_clean = line.strip()
        m_open = CHAPTER_OPENER_REGEX.match(line_clean)
        if m_open and "..." not in line_clean:
            num = m_open.group(1).upper()
            if num not in ['DI', 'DAN', 'KE', 'DARI', 'PADA']:
                num = ROMAN_MAP.get(num, num)
                num = str(int(num)) if num.isdigit() else num
                title = (m_open.group(2) or "").strip(" :.-–—|")
                title = re.sub(r'\s+\d+$', '', title).strip()
                return f"Bab {num}: {title}" if title else f"Bab {num}"

    return None


def is_bab1_opener(lines: list[str]) -> bool:
    """Check if page lines represent a Bab 1 / Chapter 1 opener page."""
    for l in lines[:6]:
        if re.search(r'\b(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s+([2-9]|[1-9]\d)\b', l, re.IGNORECASE):
            return False
    for idx, line in enumerate(lines[:10]):
        if re.search(r'^\s*(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s+(?:1|I|01)\b', line, re.IGNORECASE) and '...' not in line:
            return True
        if re.match(r'^\s*(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s*$', line, re.IGNORECASE) and idx + 1 < len(lines):
            if re.match(r'^\s*(?:1|I|01)\s*$', lines[idx + 1].strip(), re.IGNORECASE):
                return True
        if re.match(r'^\s*(?:1|I|01)\s*$', line, re.IGNORECASE) and idx + 1 < len(lines):
            if re.match(r'^\s*(?:Bab|Unit|Tema|Pelajaran|Pembelajaran)\s*$', lines[idx + 1].strip(), re.IGNORECASE):
                return True
    has_standalone_bab = any(l.strip().lower() == 'bab' for l in lines[:10])
    has_standalone_one = any(l.strip() in ['1', '01', 'I'] for l in lines[:10])
    if has_standalone_bab and has_standalone_one:
        return True
    return False


def find_main_content_start(raw_pages: list[tuple[int, str]]) -> int:
    """Find the exact 0-indexed page where main content (Bab 1) begins, safely skipping all front matter."""
    in_toc = False
    in_guide = False
    fm_indices: set[int] = set()

    for i, (p_num, raw) in enumerate(raw_pages[:30]):
        norm = normalize_text_fonts(raw)
        lines = [l.strip() for l in norm.split('\n') if l.strip()]
        if not lines:
            fm_indices.add(i)
            continue

        t_lower = norm.lower()

        is_fm_header = any(
            any(fmt in l.lower() for fmt in FRONT_MATTER_TITLES)
            for l in lines[:6]
        )

        has_roman = any(
            re.match(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$', tok.strip('.,()|[]'), re.IGNORECASE)
            for tok in lines[-1].split()
        )

        is_feature_guide = i < 20 and t_lower.count('merupakan kegiatan') >= 2
        is_copyright = i < 4 and any(k in t_lower for k in ['hak cipta', 'sanksi pelanggaran', 'penafian:'])

        if is_fm_header or has_roman or is_copyright or is_feature_guide:
            fm_indices.add(i)
            if 'daftar isi' in t_lower:
                in_toc = True
                in_guide = False
            elif any(k in t_lower for k in ['petunjuk penggunaan', 'ada apa di buku ini', 'penjelasan fitur']) or is_feature_guide:
                in_guide = True
                in_toc = False
            else:
                in_toc = False
                in_guide = False
        elif in_toc:
            has_toc_entries = any(
                re.search(r'\b(?:Bab|Unit|Tema|Pelajaran)\s+\d+', l, re.IGNORECASE)
                or re.search(r'\.{3,}\s*\d+', l)
                or re.search(r'\b(?:[2-9]|[1-9]\d)\s*$', l)
                for l in lines[:10]
            )
            if has_toc_entries and i < 15:
                fm_indices.add(i)
            else:
                in_toc = False
        elif in_guide:
            if i < 20 and not is_bab1_opener(lines):
                fm_indices.add(i)
            else:
                in_guide = False
        else:
            if is_bab1_opener(lines):
                break

    for i, (p_num, raw) in enumerate(raw_pages[:30]):
        if i in fm_indices or i < 4:
            continue
        norm = normalize_text_fonts(raw)
        lines = [l.strip() for l in norm.split('\n') if l.strip()]
        if not lines:
            continue
        return i

    return 8


def extract_pages_from_pdf(file_path: Path) -> list[PageContent]:
    """Extract pages as a list of PageContent objects with front/back matter filtering and chapter tracking."""
    pages_data: list[PageContent] = []

    try:
        logger.info("Using pdfplumber (primary extractor) for: %s", file_path.name)
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            raw_pages = [(i + 1, pdf.pages[i].extract_text() or "") for i in range(total_pages)]

        # 1. Parse TOC to obtain authoritative chapter list
        toc_chapters = parse_toc_from_pages([text for _, text in raw_pages])
        toc_map = {c.number: c for c in toc_chapters}

        # 2. Pinpoint Chapter 1 start page
        main_start_idx = find_main_content_start(raw_pages)
        logger.info("Main content start confirmed at Page %d", main_start_idx + 1)

        # 3. Extract body pages and track active chapter
        current_chapter: ChapterInfo | None = toc_map.get('1') or (toc_chapters[0] if toc_chapters else ChapterInfo(number='1', title='', full_label='Bab 1'))

        for i in range(main_start_idx, total_pages):
            p_num, raw_text = raw_pages[i]
            norm = normalize_text_fonts(raw_text)
            lines = [l.strip() for l in norm.split('\n') if l.strip()]
            if not lines:
                continue

            # Back matter detection (only in last 30% of document)
            if i > total_pages * 0.70:
                is_bm = False
                for l in lines[:4]:
                    l_lower = l.lower()
                    if any(bm in l_lower for bm in BACK_MATTER_TITLES):
                        is_bm = True
                        break
                if is_bm:
                    logger.info("Back-matter reached at Page %d, stopping extraction.", p_num)
                    break

            ch_open = detect_chapter_opener(norm, toc_map)
            if ch_open:
                current_chapter = ch_open
            else:
                ch_run = detect_chapter_running_header(norm, toc_map)
                if ch_run:
                    current_chapter = ch_run

            cleaned = clean_text(raw_text)
            if cleaned:
                pages_data.append(
                    PageContent(
                        page_number=p_num,
                        text=cleaned,
                        chapter=current_chapter.full_label if current_chapter else None
                    )
                )

        logger.info("Extracted %d main content pages out of %d total pages", len(pages_data), total_pages)

    except Exception as e:
        logger.warning("pdfplumber extraction encountered an issue (%s), falling back to pypdf", e)
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        raw_pages = [(i + 1, reader.pages[i].extract_text() or "") for i in range(total_pages)]

        toc_chapters = parse_toc_from_pages([text for _, text in raw_pages])
        toc_map = {c.number: c for c in toc_chapters}

        main_start_idx = find_main_content_start(raw_pages)
        current_chapter = toc_map.get('1') or (toc_chapters[0] if toc_chapters else ChapterInfo(number='1', title='', full_label='Bab 1'))

        for i in range(main_start_idx, total_pages):
            p_num, raw_text = raw_pages[i]
            norm = normalize_text_fonts(raw_text)
            lines = [l.strip() for l in norm.split('\n') if l.strip()]
            if not lines:
                continue

            if i > total_pages * 0.70:
                is_bm = False
                for l in lines[:4]:
                    if any(bm in l.lower() for bm in BACK_MATTER_TITLES):
                        is_bm = True
                        break
                if is_bm:
                    break

            ch_open = detect_chapter_opener(norm, toc_map)
            if ch_open:
                current_chapter = ch_open
            else:
                ch_run = detect_chapter_running_header(norm, toc_map)
                if ch_run:
                    current_chapter = ch_run

            cleaned = clean_text(raw_text)
            if cleaned:
                pages_data.append(
                    PageContent(
                        page_number=p_num,
                        text=cleaned,
                        chapter=current_chapter.full_label if current_chapter else None
                    )
                )

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
