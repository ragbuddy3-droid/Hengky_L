"""Structure Chunker - Layout & Document Hierarchy Based Chunking Strategy."""
import time
import logging
import re
from collections import Counter

from app.ingestion.base import BaseChunker, ChunkResult, PedagogicalCategory

logger = logging.getLogger(__name__)

# Section modes mapping to ensure compatibility with downstream question generation
KNOWN_SECTION_CATEGORIES = {
    "latihan": PedagogicalCategory.EVALUASI,
    "soal": PedagogicalCategory.EVALUASI,
    "ujian": PedagogicalCategory.EVALUASI,
    "evaluasi": PedagogicalCategory.EVALUASI,
    "penilaian": PedagogicalCategory.EVALUASI,
    "uji kompetensi": PedagogicalCategory.EVALUASI,
    "uji pemahaman": PedagogicalCategory.EVALUASI,
    "refleksi": PedagogicalCategory.EVALUASI,
    "mari refleksikan": PedagogicalCategory.EVALUASI,
    "apa yang sudah aku pelajari": PedagogicalCategory.EVALUASI,
    "ayo mengamati": PedagogicalCategory.INSTRUKSI,
    "ayo menyelidiki": PedagogicalCategory.INSTRUKSI,
    "ayo mencoba": PedagogicalCategory.INSTRUKSI,
    "mari mencoba": PedagogicalCategory.INSTRUKSI,
    "ayo diskusi": PedagogicalCategory.INSTRUKSI,
    "ayo berdiskusi": PedagogicalCategory.INSTRUKSI,
    "tugas": PedagogicalCategory.INSTRUKSI,
    "ayo berkarya": PedagogicalCategory.INSTRUKSI,
    "lakukan bersama": PedagogicalCategory.INSTRUKSI,
}

def is_chapter_heading(line: str) -> tuple[bool, str | None]:
    """Detect if line is a Chapter/Unit/Pembelajaran heading."""
    line_clean = line.strip()
    match = re.match(r'^(Bab|Chapter|Unit|Pembelajaran|Modul)\s+([\dIVX]+|\d+)\b(.*)$', line_clean, re.IGNORECASE)
    if match and '|' not in line_clean and '...' not in line_clean:
        ch_word = match.group(1).capitalize()
        ch_num = match.group(2)
        rest = match.group(3).strip()
        if rest:
            rest = rest.lstrip(":.-\t ")
            return True, f"{ch_word} {ch_num}: {rest}"
        return True, f"{ch_word} {ch_num}"
    return False, None

def is_section_heading(line: str) -> bool:
    """Detect if a line is a section heading based on structural rules."""
    line_clean = line.strip()
    if not line_clean:
        return False
        
    line_lower = line_clean.lower()
    
    # Check known section titles
    for key in KNOWN_SECTION_CATEGORIES:
        if line_lower.startswith(key):
            return True

    # Check sub-topic numbering like 1.1, A., B., 1. Topik
    if re.match(r'^\d+(\.\d+)*[\s\.]|^[A-Z]\.[\s]', line_clean) and len(line_clean.split()) <= 12:
        return True

    # Heading heuristics: 2-8 words, no trailing punctuation (.,:;), capitalized start, no conjunction start
    words = line_clean.split()
    if 2 <= len(words) <= 8 and line_clean[-1] not in ".!?,:;":
        if words[0].lower() not in ["dan", "atau", "karena", "pada", "dalam", "dengan", "untuk", "yang"]:
            if not any(w in line_lower for w in ["adalah", "merupakan", "yaitu"]):
                if words[0][0].isupper() or words[0][0].isdigit():
                    return True
                    
    return False

def determine_category(section_heading: str, chunk_text: str) -> PedagogicalCategory:
    """Determine category based on structural context."""
    sec_lower = (section_heading or "").lower()
    for key, cat in KNOWN_SECTION_CATEGORIES.items():
        if key in sec_lower:
            return cat
            
    text_lower = chunk_text.lower()
    if any(k in text_lower for k in ["soal", "latihan", "jawablah", "refleksi", "uji kompetensi", "menjawab pertanyaan", "pertanyaan berikut", "tuliskan organ", "buat rangkuman", "rangkuman dengan menjawab"]):
        return PedagogicalCategory.EVALUASI
    if any(k in text_lower for k in ["langkah-langkah", "lakukan", "amatilah", "diskusikan", "buatlah", "tuliskan", "bagan alur"]):
        return PedagogicalCategory.INSTRUKSI
        
    return PedagogicalCategory.KONSEP

class StructureChunker(BaseChunker):
    """Chunker strategy that relies strictly on structural document boundaries."""

    def chunk(self, text: str, max_chunk_size: int = 1000) -> list[ChunkResult]:
        """Split text into structural chunks preserving section integrity."""
        start_time = time.time()
        lines = text.split('\n')
        chunks: list[ChunkResult] = []
        
        current_chapter = "Bab 1"
        current_section = "Materi Utama"
        
        current_blocks: list[str] = []
        min_word_threshold = 15  # Minimum words per chunk
        
        i = 0
        while i < len(lines):
            line_str = lines[i].strip()
            if not line_str:
                i += 1
                continue
                
            # 1. Check Chapter Heading
            is_ch, ch_title = is_chapter_heading(line_str)
            
            # Handle multi-line Chapter heading (e.g. line 1: "Bab", line 2: "1", line 3: "Judul Bab")
            if not is_ch and re.match(r'^(Bab|Chapter|Unit|Pembelajaran|Modul)\b', line_str, re.IGNORECASE):
                ch_word = line_str.split()[0].capitalize()
                ch_num = None
                ch_rest = ""
                consumed = 1
                for j in range(1, 4):
                    if i + j < len(lines):
                        l_ahead = lines[i+j].strip()
                        num_m = re.match(r'^([\dIVX]+|\d+)$', l_ahead)
                        if num_m:
                            ch_num = num_m.group(1)
                            consumed = j + 1
                            if i + j + 1 < len(lines):
                                rest_m = lines[i+j+1].strip()
                                if rest_m and len(rest_m.split()) <= 10 and not is_section_heading(rest_m):
                                    ch_rest = rest_m
                                    consumed = j + 2
                            break
                if ch_num:
                    is_ch = True
                    ch_title = f"{ch_word} {ch_num}"
                    if ch_rest:
                        ch_title += f": {ch_rest}"
                    i += consumed - 1  # Will be incremented at bottom of loop
                    
            if is_ch and ch_title:
                # Flush current buffer
                if current_blocks:
                    block_text = "\n".join(current_blocks)
                    if len(block_text.split()) >= min_word_threshold:
                        cat = determine_category(current_section, block_text)
                        chunks.append(ChunkResult(block_text, cat, current_section, current_chapter))
                    current_blocks = []

                current_chapter = ch_title
                current_section = ch_title
                logger.info("  [StructureChunker] Chapter detected: '%s'", current_chapter)
                i += 1
                continue

            # 2. Check Section Heading
            if is_section_heading(line_str):
                if current_blocks:
                    block_text = "\n".join(current_blocks)
                    if len(block_text.split()) >= min_word_threshold:
                        cat = determine_category(current_section, block_text)
                        chunks.append(ChunkResult(block_text, cat, current_section, current_chapter))
                    current_blocks = []

                current_section = line_str
                logger.debug("  [StructureChunker] Section detected: '%s'", current_section)
                i += 1
                continue

            # 3. Regular block accumulation
            current_blocks.append(line_str)
            accumulated_chars = sum(len(b) for b in current_blocks) + len(current_blocks)
            accumulated_words = sum(len(b.split()) for b in current_blocks)

            # Check if accumulated chunk reaches target size limit (~max_chunk_size chars or ~250 words)
            if accumulated_chars >= max_chunk_size or accumulated_words >= (max_chunk_size / 4):
                block_text = "\n".join(current_blocks)
                cat = determine_category(current_section, block_text)
                chunks.append(ChunkResult(block_text, cat, current_section, current_chapter))
                current_blocks = []

            i += 1

        # Flush final buffer
        if current_blocks:
            block_text = "\n".join(current_blocks)
            if len(block_text.split()) >= min_word_threshold:
                cat = determine_category(current_section, block_text)
                chunks.append(ChunkResult(block_text, cat, current_section, current_chapter))

        elapsed = time.time() - start_time
        cat_counts = Counter(c.category.value for c in chunks)
        dist_str = ", ".join(f"{k}={v}" for k, v in sorted(cat_counts.items()))
        logger.info("Structure Chunking complete: %d chunks created in %.2fs. Distribution: %s",
                    len(chunks), elapsed, dist_str)

        return chunks
