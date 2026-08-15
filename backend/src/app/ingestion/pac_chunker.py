"""Pedagogical Adaptive Chunking (PAC)."""
import time
import logging
from enum import Enum
import re
from collections import Counter

from app.ingestion.base import BaseChunker, ChunkResult, PedagogicalCategory

logger = logging.getLogger(__name__)

class BlockType(Enum):
    HEADING = "HEADING"
    LIST = "LIST"
    PARAGRAPH = "PARAGRAPH"

# Dictionaries & Discourse Markers from PA-Chunking.md
IMPERATIVE_VERBS = {
    "amati", "amatilah", "perhatikan", "lakukan", "siapkan", "diskusikan",
    "tuliskan", "jawablah", "sebutkan", "urutkan", "pasangkan",
    "buatlah", "bacalah", "cermati", "pahami", "gunakan",
    "kerjakan", "cobalah", "tentukan", "prediksi", "isilah",
    "lengkapilah", "tebaklah", "ukur", "gambar", "hitung",
    "jelaskan", "uraikan", "pilihlah", "lingkarilah"
}

EVAL_TRIGGERS = {
    "latihan", "soal", "ujian",
    "jawablah", "isilah", "pasangkan", "urutkan", "pilihlah",
    "lengkapilah", "teka-teki silang", "diagram venn",
    "refleksikan", "refleksi", "mari refleksikan", "mari refleksi",
    "evaluasi", "penilaian", "apa yang sudah aku pelajari",
    "menjawab pertanyaan", "pertanyaan berikut", "soal berikut",
    "buat rangkuman", "rangkuman dengan menjawab", "tugas individu", "tugas kelompok"
}

PROMPT_WORDS = {
    "tahukah", "yuk", "mari", "pernahkah", "selamat belajar", "masih ingat"
}

DEFAULT_SECTION_MODES = {
    "ayo mengamati": "INSTRUKSI",
    "ayo menyelidiki": "INSTRUKSI",
    "ayo menyimpulkan": "INSTRUKSI",
    "ayo membaca": "KONSEP",
    "ayo memahami": "KONSEP",
    "ayo mencoba": "INSTRUKSI",
    "mari mencoba": "INSTRUKSI",
    "ayo diskusi": "INSTRUKSI",
    "ayo berdiskusi": "INSTRUKSI",
    "ayo mencari tahu": "INSTRUKSI",
    "ayo menggambar": "INSTRUKSI",
    "ayo kampanye": "INSTRUKSI",
    "ayo tampilkan": "INSTRUKSI",
    "ayo berkarya": "INSTRUKSI",
    "lakukan bersama": "INSTRUKSI",
    "tugas": "INSTRUKSI",
    "ayo mengingat kembali": "EVALUASI",
    "ayo merenungkan": "EVALUASI",
    "ayo kamu bisa": "EVALUASI",
    "mari refleksikan": "EVALUASI",
    "refleksi": "EVALUASI",
    "releksi": "EVALUASI",
    "uji kompetensi": "EVALUASI",
    "uji pemahaman": "EVALUASI",
    "apa yang sudah aku pelajari": "EVALUASI",
}

def is_rule_heading(line: str) -> bool:
    """Check heading rule (2-6 words, no trailing punctuation, no mid-conjunction/definition, capitalized)."""
    line_clean = line.strip()
    words = line_clean.split()
    
    if not (2 <= len(words) <= 8):
        return False
        
    if line_clean[-1] in ".!?,:;":
        return False
        
    start_word = words[0].lower()
    if start_word in ["dan", "atau", "karena", "pada", "dalam", "dengan", "untuk"]:
        return False
        
    line_lower = line_clean.lower()
    if any(w in line_lower for w in ["adalah", "merupakan", "yaitu", "karena"]):
        return False
        
    first_char = words[0][0]
    if not (first_char.isupper() or first_char.isdigit()):
        return False
        
    return True

def classify_line(line: str) -> BlockType:
    """Rule-based line classification per PA-Chunking.md."""
    line = line.strip()
    if not line:
        return BlockType.PARAGRAPH

    line_lower = line.lower()
    
    if re.match(r'^(Bab|Chapter|Unit|Pembelajaran|Modul)\s+([\dIVX]+|\d+)\b', line, re.IGNORECASE):
        return BlockType.HEADING

    for sec_name in DEFAULT_SECTION_MODES:
        if line_lower.startswith(sec_name):
            return BlockType.HEADING

    if re.match(r'^\d+(\.\d+)*[\s\.]|^[A-Z]\.[\s]', line) and len(line.split()) <= 10:
        return BlockType.HEADING

    if is_rule_heading(line):
        return BlockType.HEADING

    if re.match(r'^[\-\*\•]\s|^\d+[\.\)]\s|^[a-zA-Z][\.\)]\s', line):
        return BlockType.LIST

    return BlockType.PARAGRAPH

def detect_heading_level(line: str) -> tuple[bool, str]:
    """Detect if a heading is Chapter vs Section heading."""
    if re.match(r'^(Bab|Chapter|Unit|Pembelajaran|Modul)\s+([\dIVX]+|\d+)\b', line, re.IGNORECASE) and '|' not in line and '...' not in line:
        return True, "chapter"
    return False, "section"

def looks_like_evaluative(text: str) -> bool:
    """Check if text fits EVALUATIVE_QUESTION discourse marker."""
    text_lower = text.lower()
    if any(t in text_lower for t in EVAL_TRIGGERS):
        if '?' in text or '!' in text or re.search(r'\d+[\.\)]\s', text) or re.search(r'[a-e][\.\)]\s', text_lower):
            return True
        if any(kw in text_lower for kw in ['refleksi', 'uji pemahaman', 'uji kompetensi', 'apa yang sudah aku pelajari', 'menjawab pertanyaan', 'pertanyaan berikut']):
            return True

    # Detect multi-question sub-item patterns (e.g. "a. Tuliskan...", "b. Jelaskan...", "c. Buatkan...")
    sub_questions = re.findall(r'[a-e1-9][\.\)]\s*(tuliskan|jelaskan|sebutkan|buatlah|buatkan|isilah|urutkan|pasangkan|bagaimana|mengapa|apa)', text_lower)
    if len(sub_questions) >= 2 or ("menjawab pertanyaan" in text_lower and len(sub_questions) >= 1):
        return True

    return False

def classify_pedagogy(text: str, current_section_mode: str = None) -> PedagogicalCategory:
    """Classify text using discourse markers & category mapping per PA-Chunking.md."""
    text_lower = text.lower()
    
    if current_section_mode:
        if current_section_mode == "EVALUASI":
            return PedagogicalCategory.EVALUASI
        elif current_section_mode == "INSTRUKSI":
            return PedagogicalCategory.INSTRUKSI
            
    if looks_like_evaluative(text):
        return PedagogicalCategory.EVALUASI

    if any(p in text_lower for p in PROMPT_WORDS):
        return PedagogicalCategory.INSTRUKSI

    words = set(re.findall(r'\b\w+\b', text_lower))
    if words.intersection(IMPERATIVE_VERBS):
        return PedagogicalCategory.INSTRUKSI

    if re.search(r'\b(adalah|merupakan|yaitu|disebut)\b', text_lower):
        return PedagogicalCategory.KONSEP

    if re.search(r'\b(karena|sehingga|oleh karena itu)\b', text_lower):
        return PedagogicalCategory.KONSEP

    if re.search(r'\b(misalnya|contohnya|seperti)\b', text_lower):
        return PedagogicalCategory.KONSEP

    if re.search(r'\b(dahulu|suatu hari|kemudian|tinggallah)\b', text_lower):
        return PedagogicalCategory.NARASI

    if "kosakata baru" in text_lower:
        return PedagogicalCategory.KONSEP

    return PedagogicalCategory.KONSEP

class PAChunker(BaseChunker):
    """Pedagogical Adaptive Chunking (PAC) strategy implementation."""

    def chunk(self, text: str, max_chunk_size: int = 1000) -> list[ChunkResult]:
        """Implement 5-stage PAC algorithm using Context State mechanism."""
        start_time = time.time()
        input_chars = len(text)
        input_lines = text.count('\n') + 1
        logger.info("Starting PAC chunking (input=%s chars, %d lines, max_chunk_size=%d)",
                    f"{input_chars:,}", input_lines, max_chunk_size)
        
        lines = text.split('\n')
        chunks = []
        
        current_chapter = "Bab 1"
        current_section = "Materi Utama"
        current_section_mode = None
        
        current_chunk_blocks = []
        current_chunk_category = None
        
        min_word_threshold = 15  # Minimum words per valid chunk
        
        i = 0
        while i < len(lines):
            line_str = lines[i].strip()
            if not line_str:
                i += 1
                continue
                
            is_chapter = False
            full_ch_title = None
            consumed = 1
            
            if re.match(r'^(Bab|Chapter|Unit|Pembelajaran|Modul)\b', line_str, re.IGNORECASE) and '|' not in line_str and '...' not in line_str:
                ch_num = None
                m_inline = re.search(r'\b(Bab|Chapter|Unit|Pembelajaran|Modul)\s+([\dIVX]+|\d+)\b', line_str, re.IGNORECASE)
                
                if m_inline:
                    ch_num = m_inline.group(2)
                    ch_word = m_inline.group(1).capitalize()
                else:
                    ch_word = line_str.split()[0].capitalize()
                    for j in range(1, 5):
                        if i + j < len(lines):
                            l_ahead = lines[i+j].strip()
                            m_ahead = re.match(r'^([\dIVX]+|\d+)$', l_ahead)
                            if m_ahead:
                                ch_num = m_ahead.group(1)
                                consumed = j + 1
                                break
                                
                if ch_num:
                    is_chapter = True
                    full_ch_title = f"{ch_word} {ch_num}"
                        
            if is_chapter and full_ch_title:
                if current_chunk_blocks:
                    chunk_str = "\n".join(current_chunk_blocks)
                    if len(chunk_str.split()) >= min_word_threshold:
                        cat = current_chunk_category or classify_pedagogy(chunk_str, current_section_mode)
                        chunks.append(ChunkResult(chunk_str, cat, current_section, current_chapter))
                    current_chunk_blocks = []
                    current_chunk_category = None

                current_chapter = full_ch_title
                current_section = full_ch_title
                current_section_mode = None
                logger.info("  Chapter detected: '%s' (consumed %d lines)", current_chapter, consumed)
                i += consumed
                continue
                
            block_type = classify_line(line_str)
            
            if block_type == BlockType.HEADING:
                if current_chunk_blocks:
                    chunk_str = "\n".join(current_chunk_blocks)
                    if len(chunk_str.split()) >= min_word_threshold:
                        cat = current_chunk_category or classify_pedagogy(chunk_str, current_section_mode)
                        chunks.append(ChunkResult(chunk_str, cat, current_section, current_chapter))
                    current_chunk_blocks = []
                    current_chunk_category = None

                current_section = line_str
                line_lower = line_str.lower()
                current_section_mode = None
                for sec_name, mode in DEFAULT_SECTION_MODES.items():
                    if line_lower.startswith(sec_name):
                        current_section_mode = mode
                        break
                logger.debug("  Section detected: '%s' (mode=%s)", current_section, current_section_mode)
            else:
                block_cat = classify_pedagogy(line_str, current_section_mode)
                
                if current_chunk_category is not None and block_cat != current_chunk_category:
                    accumulated_words = sum(len(b.split()) for b in current_chunk_blocks)
                    if accumulated_words >= min_word_threshold:
                        chunk_str = "\n".join(current_chunk_blocks)
                        chunks.append(ChunkResult(chunk_str, current_chunk_category, current_section, current_chapter))
                        current_chunk_blocks = []
                        current_chunk_category = block_cat
                
                if current_chunk_category is None:
                    current_chunk_category = block_cat
                    
                current_chunk_blocks.append(line_str)
                
                accumulated_words = sum(len(b.split()) for b in current_chunk_blocks)
                if accumulated_words >= (max_chunk_size / 4):
                    chunk_str = "\n".join(current_chunk_blocks)
                    chunks.append(ChunkResult(chunk_str, current_chunk_category, current_section, current_chapter))
                    current_chunk_blocks = []
                    current_chunk_category = None

            i += 1
                    
        if current_chunk_blocks:
            chunk_str = "\n".join(current_chunk_blocks)
            if len(chunk_str.split()) >= min_word_threshold:
                cat = current_chunk_category or classify_pedagogy(chunk_str, current_section_mode)
                chunks.append(ChunkResult(chunk_str, cat, current_section, current_chapter))

        elapsed = time.time() - start_time
        
        cat_counts = Counter(c.category.value for c in chunks)
        dist_str = ", ".join(f"{k}={v}" for k, v in sorted(cat_counts.items()))
        logger.info("PAC Chunking complete: %d high-quality chunks created in %.2fs. Distribution: %s",
                    len(chunks), elapsed, dist_str)
        
        return chunks

def chunk_text(text: str, max_chunk_size: int = 1000, **kwargs) -> list[ChunkResult]:
    """Top-level helper function for backward compatibility."""
    return PAChunker().chunk(text, max_chunk_size)
