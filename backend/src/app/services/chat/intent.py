"""Detect question-generation requests in chat messages and extract their parameters."""

import logging
import re

from app.schemas.api_schemas import GenerateParams
from app.services.generation.planner import MIXED_BLOOM_LEVELS

logger = logging.getLogger(__name__)

# SD only covers C1-C4; C5/C6 in a message are ignored (falls back to mixed levels)
BLOOM_MAPPING = {level[:2]: level for level in MIXED_BLOOM_LEVELS}

MAX_QUESTIONS_PER_REQUEST = 20
DEFAULT_NUM_QUESTIONS = 5


def is_generation_intent(text: str) -> bool:
    """Whether the message asks for questions to be generated."""
    if not text:
        return False
    t = text.lower().strip()

    # 1. Generation verb followed by a question noun: "buatkan 3 soal", "tolong bikin pertanyaan"
    if re.search(r'\b(?:buat(?:kan)?|bikin|generate|minta|tulis(?:kan)?|susun|ciptakan|tolong)\b.*\b(?:soal|pertanyaan|latihan|kuis|ujian)\b', t):
        return True

    # 2. Number + question noun: "3 soal", "10 soal esai"
    if re.search(r'\b\d+\s*(?:soal|pertanyaan|latihan|kuis)\b', t):
        return True

    # 3. Bloom level code with an educational keyword: "soal c2", "c4 bab 3"
    if re.search(r'\b(c[1-4])\b', t) and any(w in t for w in ['soal', 'bab', 'esai', 'isian', 'buat', 'materi', 'level']):
        return True

    # 4. Question type with generation/chapter context
    if any(q_type in t for q_type in ['esai', 'isian singkat', 'isian', 'pilihan ganda']) and any(
        w in t for w in ['buat', 'bikin', 'bab', 'soal', 'minta', 'tolong']
    ):
        return True

    # 5. Question noun + topic/chapter/level
    return bool(
        any(w in t for w in ['soal', 'pertanyaan'])
        and any(w in t for w in ['bab', 'materi', 'tema', 'c1', 'c2', 'c3', 'c4', 'tingkat', 'level'])
    )


def parse_generation_params(text: str) -> GenerateParams:
    """Extract number of questions, Bloom level and chapter from a natural-language request."""
    num_questions = DEFAULT_NUM_QUESTIONS
    bloom_level = None
    chapter = None

    match_num = re.search(r'(\d+)\s*(?:soal|pertanyaan)', text, re.IGNORECASE)
    if match_num:
        num_questions = max(1, min(MAX_QUESTIONS_PER_REQUEST, int(match_num.group(1))))

    match_bloom = re.search(r'\b(C[1-4])\b', text, re.IGNORECASE)
    if match_bloom:
        bloom_level = BLOOM_MAPPING.get(match_bloom.group(1).upper())

    match_chap = re.search(r'\bbab\s*([\w]+|[IVXLCDM]+)', text, re.IGNORECASE)
    if match_chap:
        chapter = match_chap.group(1)

    logger.debug("Parsed generation params: num_questions=%d, bloom_level=%s, chapter=%s", num_questions, bloom_level, chapter)
    return GenerateParams(num_questions=num_questions, chapter=chapter, bloom_level=bloom_level)
