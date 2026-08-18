"""Shared pedagogical text classifiers for all chunking strategies."""

import re


def classify_chunk_category(text: str) -> str:
    """Classify text chunk into pedagogical categories."""
    lower = text.lower()
    eval_keywords = [
        "latihan", "soal", "uji kompetensi", "evaluasi",
        "jawablah", "pilihlah jawaban", "tugas individu",
    ]
    instr_keywords = [
        "amati", "lakukan", "diskusikan", "buatlah",
        "tugas kelompok", "ayo mencoba", "petunjuk", "langkah",
    ]
    konsep_patterns = [
        r"\b(adalah|merupakan|yaitu|artinya|didefinisikan sebagai|terdiri atas|fungsi dari|organ|sistem)\b"
    ]

    if any(k in lower for k in eval_keywords):
        return "Evaluasi"
    if any(k in lower for k in instr_keywords):
        return "Instruksi"
    if any(re.search(pat, lower) for pat in konsep_patterns):
        return "Konsep"
    return "Narasi"


def extract_chapter_and_heading(
    text: str,
    prev_chapter: str | None,
    prev_heading: str | None,
) -> tuple[str | None, str | None]:
    """Extract or inherit chapter and heading from text lines."""
    chapter = prev_chapter
    heading = prev_heading

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[:3]:
        chap_match = re.search(
            r"\b(Bab|Chapter|Unit|Pembelajaran|Modul)\s+([\w\d]+)",
            line,
            re.IGNORECASE,
        )
        if chap_match:
            chapter = chap_match.group(0)

        if (
            2 <= len(line.split()) <= 8
            and not line.endswith((".", ":", "?", "!"))
            and not re.search(r"^(gambar|tabel|sumber)\b", line, re.IGNORECASE)
        ):
            heading = line

    return chapter, heading
