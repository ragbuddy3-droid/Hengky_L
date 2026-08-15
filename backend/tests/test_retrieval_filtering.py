"""Unit tests for query sanitization and anti-exercise chunk filtering."""
import pytest
from app.pipeline.orchestrator import _sanitize_retrieval_query, _is_exercise_or_instruction_chunk
from app.ingestion.pac_chunker import looks_like_evaluative
from app.ingestion.structure_chunker import determine_category, PedagogicalCategory

def test_sanitize_retrieval_query():
    raw_prompt = "Buatkan 5 soal C4 bab 2 organ pernapasan"
    cleaned = _sanitize_retrieval_query(raw_prompt)
    assert "buatkan" not in cleaned
    assert "soal" not in cleaned
    assert "c4" not in cleaned
    assert "organ pernapasan" in cleaned

def test_is_exercise_or_instruction_chunk():
    exercise_chunk = (
        "Buat rangkuman dengan menjawab pertanyaan berikut:\n"
        "a. Tuliskan organ-organ yang terlibat dalam pernapasan!\n"
        "b. Jelaskan dengan menggunakan bahasamu, fungsi dari setiap organnya!\n"
        "c. Buatkan bagan alur perjalanan udara di dalam tubuhmu!"
    )
    assert _is_exercise_or_instruction_chunk(exercise_chunk) is True

    concept_chunk = (
        "Organ pernapasan manusia terdiri atas hidung, tenggorokan (faring dan laring), "
        "trakea, bronkus, dan paru-paru. Udara masuk melalui hidung dan disaring oleh bulu hidung. "
        "Di dalam paru-paru terjadi pertukaran gas oksigen dan karbon dioksida."
    )
    assert _is_exercise_or_instruction_chunk(concept_chunk) is False

def test_chunker_evaluative_detection():
    exercise_text = (
        "Jawablah pertanyaan berikut:\n"
        "1. Tuliskan nama-nama organ pernapasan!\n"
        "2. Jelaskan fungsi diafragma!"
    )
    assert looks_like_evaluative(exercise_text) is True
    cat = determine_category("Materi Utama", exercise_text)
    assert cat == PedagogicalCategory.EVALUASI
