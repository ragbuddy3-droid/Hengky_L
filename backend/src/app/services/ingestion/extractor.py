"""PDF text extraction module with page-aware front-matter and back-matter filtering."""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from app.services.ingestion.chunkers.classifiers import ROMAN_MAP

logger = logging.getLogger(__name__)

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
    # Running headers/footers: "Bab 4 Belajar Bermusyawarah 91", "112 Pendidikan Pancasila untuk SD/MI Kelas VI"
    r'(?i)^(?:\d{1,3}\s+)?Bab\s+\d{1,2}\s*\|?\s*[A-Z].{2,90}\s+\d{1,3}$',
    r'(?i)^(?:\d{1,3}\s+)?[A-Z][\w ,]{3,80}untuk\s+SD\s*/\s*MI\s+Kelas\s+[IVX]+(?:\s*\(Edisi Revisi\))?(?:\s+\d{1,3})?$',
]

# URLs, including ones the PDF wrapped onto the next line ("https://buku.kemdikbud.\ngo.id/s/...")
URL_REGEX = re.compile(
    r'(?:https?://|www\.)\S*(?:(?<=[./\-])\n\S+)*|\b(?:s\.id|bit\.ly|youtu\.be|youtube\.com)/\S+',
    re.IGNORECASE,
)
# Book-navigation instructions ("Pindai barcode di samping untuk membaca ...") are not subject matter
NAVIGATION_REGEX = re.compile(
    r'\b(?:barcode|bar\s*code|kode\s+qr|qr\s*code|pindai\w*|memindai|scan|tautan|klik|link)\b',
    re.IGNORECASE,
)
NAVIGATION_SENTENCE_MAX_CHARS = 300

CHAPTER_KEYWORDS = r'(?:Bab|Unit|Tema|Modul|Pelajaran|Pembelajaran)'
CHAPTER_NUMBER = r'([0-9]{1,2}|[IVX]{1,5})\b'

# Running header/footer line: "Bab 4 | Judul 91", "Bab 4 Judul 91", "12 Bab 4 Judul", "BAB 2: Judul"
CHAPTER_RUNNING_REGEX = re.compile(
    rf'^\s*(?:\d{{1,3}}\s+)?{CHAPTER_KEYWORDS}\s*{CHAPTER_NUMBER}\s*[|:]?\s*([A-Za-z].{{2,90}}?)\s*\d{{0,3}}\s*$',
    re.IGNORECASE | re.MULTILINE,
)
# Chapter opener line anchored at the start, so prose like "Ingat, di Bab 2 kamu ..." never matches
CHAPTER_OPENER_REGEX = re.compile(
    rf'^\s*{CHAPTER_KEYWORDS}\s+{CHAPTER_NUMBER}(?:\s*[:.|\-–—]?\s*(.*))?$',
    re.IGNORECASE,
)
MIN_TITLE_VOTES = 3
MAX_TITLE_CHARS = 80


@dataclass
class ChapterInfo:
    """Structured chapter metadata."""
    number: int
    title: str


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


def to_chapter_number(raw: str) -> int | None:
    """'3', '03', 'III' -> 3; anything else (or 0) -> None."""
    raw = raw.strip().upper()
    value = ROMAN_MAP.get(raw, raw)
    return int(value) if value.isdigit() and int(value) > 0 else None


def clean_chapter_title(title: str) -> str:
    """Strip separators, a trailing page number and repeated whitespace from a chapter title."""
    title = re.sub(r'\s+', ' ', title).strip(" :.-–—|")
    return re.sub(r'\s+\d{1,3}$', '', title).strip(" :.-–—|")


def chapter_label(number: int, title: str | None) -> str:
    return f"Bab {number}: {title}" if title else f"Bab {number}"


def is_valid_toc_title(title: str) -> bool:
    """Reject TOC titles mangled by multi-column layouts ('Kata Pengantar iii Mengamalkan ...', '... 1. Indahnya ...')."""
    if not 3 <= len(title) <= MAX_TITLE_CHARS:
        return False
    if re.search(r'(?i)kata pengantar|prakata|daftar|glosarium|pengenalan tokoh|penjelasan fitur', title):
        return False
    if re.search(r'\b(?:ii|iii|iv|vi|vii|viii|ix|xi|xii|xiii|xiv)\b', title):  # roman page numbers
        return False
    return not re.search(r'(?:^|\s)(?:\d{1,2}|[A-Z])\.\s', title)  # sub-items "1. ..." / "A. ..."


def _title_key(title: str) -> str:
    return re.sub(r'[^a-z0-9]', '', title.lower())


def same_title(a: str, b: str) -> bool:
    """Loose title equality: ignores case/punctuation and tolerates a truncated or extended variant."""
    ka, kb = _title_key(a), _title_key(b)
    if len(ka) < 4 or len(kb) < 4:
        return ka == kb
    return ka.startswith(kb) or kb.startswith(ka)


def parse_toc_from_pages(page_norms: list[str]) -> list[ChapterInfo]:
    """Parse the Table of Contents (Daftar Isi) from the early, font-normalized pages of the textbook."""
    chapters: list[ChapterInfo] = []
    in_toc = False
    toc_lines: list[str] = []

    for norm in page_norms[:15]:
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
        norm_num = to_chapter_number(m.group(1))
        if norm_num is None:
            continue
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

        title = clean_chapter_title(" ".join(title_parts))

        if not any(c.number == norm_num for c in chapters):
            chapters.append(ChapterInfo(number=norm_num, title=title))

    return chapters


def _page_lines(page_norm: str) -> list[str]:
    return [line.strip() for line in page_norm.split('\n') if line.strip()]


def _edge_lines(lines: list[str]) -> list[str]:
    """Lines where running headers/footers live (top two and bottom two), without duplicates."""
    return list(dict.fromkeys(lines[:2] + lines[-2:]))


def match_running_header(line: str) -> tuple[int, str] | None:
    """Parse a running header/footer line into (chapter number, title)."""
    if '...' in line:
        return None
    m = CHAPTER_RUNNING_REGEX.match(line)
    if not m:
        return None
    number = to_chapter_number(m.group(1))
    title = clean_chapter_title(m.group(2))
    if number is None or len(title) <= 2:
        return None
    return number, title


def vote_running_titles(page_norms: list[str], min_votes: int = MIN_TITLE_VOTES) -> dict[int, str]:
    """Most frequent running-header title per chapter number (titles seen fewer than `min_votes` times are ignored)."""
    votes: Counter[tuple[int, str]] = Counter()
    for norm in page_norms:
        for line in _edge_lines(_page_lines(norm)):
            parsed = match_running_header(line)
            if parsed:
                votes[parsed] += 1
    titles: dict[int, str] = {}
    for (number, title), count in votes.most_common():
        if count >= min_votes and number not in titles and len(title) <= MAX_TITLE_CHARS:
            titles[number] = title
    return titles


def resolve_chapter_titles(page_norms: list[str], toc_chapters: list[ChapterInfo]) -> dict[int, str]:
    """Chapter titles by number: running-header votes win over TOC titles, which are often mangled by layout."""
    titles = {c.number: c.title for c in toc_chapters if c.title and is_valid_toc_title(c.title)}
    titles.update(vote_running_titles(page_norms))
    return titles


def _cover_title(lines: list[str]) -> str:
    """Title lines that follow the chapter number on a Kemdikbud chapter cover."""
    title_lines: list[str] = []
    for t_line in lines[:5]:
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
    return clean_chapter_title(" ".join(title_lines))


def detect_chapter_opener(page_norm: str, titles: dict[int, str], current: int = 0) -> tuple[int, str] | None:
    """Detect a chapter opening page; returns (number, title found on the page or '').

    `current` is the active chapter: a bare title match only counts for the next one, since readings inside
    a chapter may share a later chapter's title (PP Kelas 3 has a reading "Berbeda Itu Indah" in Bab 1).
    """
    lines = _page_lines(page_norm)
    if not lines:
        return None

    for idx, line in enumerate(lines[:10]):
        # 1. "Bab 1", "Bab 1: Judul", "Bab 1 | Judul" at the start of a line
        m = CHAPTER_OPENER_REGEX.match(line)
        if m and '...' not in line:
            number = to_chapter_number(m.group(1))
            inline_title = clean_chapter_title(m.group(2) or "")
            if number is not None:
                known = titles.get(number)
                if not inline_title:
                    return number, ""
                if known and same_title(inline_title, known):
                    return number, known
                if not known and len(inline_title) < 60 and inline_title[0].isupper():
                    return number, inline_title
                # "Bab 2 kamu sudah belajar ..." is prose, not an opener

        # 2. "Bab" on its own line followed by the number
        if re.match(rf'^{CHAPTER_KEYWORDS}$', line, re.IGNORECASE) and idx + 1 < len(lines):
            num_match = re.match(r'^([0-9]{1,2}|[IVX]{1,5})$', lines[idx + 1], re.IGNORECASE)
            if num_match:
                number = to_chapter_number(num_match.group(1))
                if number is not None:
                    title_cand = lines[idx + 2] if idx + 2 < len(lines) else ""
                    if len(title_cand) >= 60 or title_cand.isdigit():
                        title_cand = ""
                    return number, clean_chapter_title(title_cand)

    # 3. Kemdikbud chapter cover: "Bab" somewhere in the header block and the number on its own line
    for idx, line in enumerate(lines[:6]):
        if re.search(r'\bBab\b', line, re.IGNORECASE):
            for s_idx, sub_line in enumerate(lines[idx:idx + 6]):
                m_num = re.match(r'^\s*([0-9]{1,2}|[IVX]{1,5})\s*$', sub_line)
                if m_num:
                    number = to_chapter_number(m_num.group(1))
                    if number is not None:
                        return number, _cover_title(lines[idx + s_idx + 1: idx + s_idx + 6])

    # 4. The next chapter's title shown prominently near the top
    next_title = titles.get(current + 1, "")
    if len(next_title) > 4:
        for line in lines[:8]:
            if next_title.lower() in line.lower() and len(line) < len(next_title) + 15:
                return current + 1, next_title

    return None


def detect_chapter_running_header(page_norm: str, titles: dict[int, str]) -> tuple[int, str] | None:
    """Chapter from a running header/footer; when the title is known it must match, filtering out prose mentions."""
    for line in _edge_lines(_page_lines(page_norm)):
        parsed = match_running_header(line)
        if not parsed:
            continue
        number, title = parsed
        known = titles.get(number)
        if known is None or same_title(title, known):
            return number, known or title
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


def find_main_content_start(page_norms: list[str]) -> int:
    """Find the 0-indexed page where main content (Bab 1) begins, skipping all front matter."""
    in_toc = False
    in_guide = False
    fm_indices: set[int] = set()

    for i, norm in enumerate(page_norms[:30]):
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

    for i, norm in enumerate(page_norms[:30]):
        if i not in fm_indices and i >= 4 and norm.strip():
            return i

    return 8


def _read_raw_pages(file_path: Path) -> list[tuple[int, str]]:
    """(1-indexed page number, raw text) for every page; pdfplumber first, pypdf as fallback."""
    try:
        logger.info("Using pdfplumber (primary extractor) for: %s", file_path.name)
        with pdfplumber.open(file_path) as pdf:
            return [(i + 1, page.extract_text() or "") for i, page in enumerate(pdf.pages)]
    except Exception as e:
        logger.warning("pdfplumber extraction encountered an issue (%s), falling back to pypdf", e)
        reader = PdfReader(file_path)
        return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def _is_back_matter(lines: list[str]) -> bool:
    return any(bm in line.lower() for line in lines[:4] for bm in BACK_MATTER_TITLES)


def build_pages(raw_pages: list[tuple[int, str]]) -> list[PageContent]:
    """Trim front/back matter and attach a chapter label to every main-content page.

    Chapters only move forward: an opener must name a later chapter (at most two ahead, in case one opener
    was missed) and a running header the current or next one, so a passing mention such as
    "Ingat, di Bab 2 kamu sudah belajar ..." on a Bab 6 page can't pull the page back.
    """
    total_pages = len(raw_pages)
    page_norms = [normalize_text_fonts(text) for _, text in raw_pages]
    toc_chapters = parse_toc_from_pages(page_norms)
    main_start_idx = find_main_content_start(page_norms)
    logger.info("Main content start confirmed at Page %d", main_start_idx + 1)

    # Main-content pages up to the back matter
    body: list[tuple[int, str]] = []  # (page number, normalized text)
    for i in range(main_start_idx, total_pages):
        p_num, norm = raw_pages[i][0], page_norms[i]
        lines = _page_lines(norm)
        if not lines:
            continue
        if i > total_pages * 0.70 and _is_back_matter(lines):
            logger.info("Back-matter reached at Page %d, stopping extraction.", p_num)
            break
        body.append((p_num, norm))

    titles = resolve_chapter_titles([norm for _, norm in body], toc_chapters)
    current = 1

    pages_data: list[PageContent] = []
    for p_num, norm in body:
        opener = detect_chapter_opener(norm, titles, current)
        if opener and current < opener[0] <= current + 2:
            current = opener[0]
            titles.setdefault(current, opener[1])
        else:
            running = detect_chapter_running_header(norm, titles)
            if running and current <= running[0] <= current + 1:
                current = running[0]
                titles.setdefault(current, running[1])

        cleaned = _clean_normalized(norm)
        if cleaned:
            pages_data.append(PageContent(page_number=p_num, text=cleaned, chapter=chapter_label(current, titles.get(current))))

    logger.info("Extracted %d main content pages out of %d total pages", len(pages_data), total_pages)
    return pages_data


def extract_pages_from_pdf(file_path: Path) -> list[PageContent]:
    """Extract pages as a list of PageContent objects with front/back matter filtering and chapter tracking."""
    return build_pages(_read_raw_pages(file_path))


def _strip_url(match: re.Match[str]) -> str:
    # Keep a sentence-ending period that the URL pattern swallowed
    return "." if match.group(0).endswith(".") else ""


def drop_navigation_sentences(text: str) -> str:
    """Remove sentences that tell the reader to scan a barcode or open a link (only those lines, for long run-ons)."""
    parts = re.split(r'(?<=[.!?])(\s+)', text)
    kept: list[str] = []
    for part in parts:
        if part.strip() and NAVIGATION_REGEX.search(part):
            if len(part) <= NAVIGATION_SENTENCE_MAX_CHARS:
                continue
            part = "\n".join(line for line in part.split("\n") if not NAVIGATION_REGEX.search(line))
        kept.append(part)
    return "".join(kept)


def clean_text(text: str) -> str:
    """Remove noise lines, running headers/footers, page numbers, links, barcode instructions and excess whitespace."""
    return _clean_normalized(normalize_text_fonts(text))


def _clean_normalized(text_norm: str) -> str:
    if not text_norm:
        return ""
    cleaned_lines = []

    for line in text_norm.split('\n'):
        line_str = line.strip()
        if line_str and not any(re.match(pat, line_str, re.IGNORECASE) for pat in NOISE_PATTERNS):
            cleaned_lines.append(line_str)

    result = "\n".join(cleaned_lines)
    result = URL_REGEX.sub(_strip_url, result)
    result = drop_navigation_sentences(result)
    result = "\n".join(line.strip() for line in result.split("\n") if line.strip())
    result = re.sub(r'[ \t]{2,}', ' ', result)
    return result.strip()
