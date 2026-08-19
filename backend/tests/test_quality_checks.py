"""Tests for post-generation quality heuristics."""

from app.services.validation.quality_checks import validate_answer_quality


def test_short_essay_answer_flagged():
    """Essay questions with answer under 5 words should be flagged."""
    q = {
        "question": "Jelaskan proses fotosintesis?",
        "question_type": "esai",
        "answer": "Proses tumbuhan",  # 2 words
    }
    issues = validate_answer_quality(q)
    assert any("terlalu pendek" in issue for issue in issues)


def test_long_isian_answer_flagged():
    """Short answer with answer over 25 words should be flagged."""
    long_ans = " ".join(["kata"] * 26)
    q = {
        "question": "Sebutkan nama ibu kota Indonesia?",
        "question_type": "isian_singkat",
        "answer": long_ans,
    }
    issues = validate_answer_quality(q)
    assert any("terlalu panjang" in issue for issue in issues)


def test_missing_question_mark_flagged():
    """Questions without ending question mark or exclamation mark should be flagged."""
    q = {
        "question": "Sebutkan 3 jenis hewan mamalia",
        "question_type": "esai",
        "answer": "Kucing, anjing, dan sapi merupakan contoh hewan mamalia yang melahirkan.",
    }
    issues = validate_answer_quality(q)
    assert any("tidak diakhiri tanda tanya" in issue for issue in issues)


def test_valid_question_no_issues():
    """Well-formed questions should pass quality checks with 0 issues."""
    q = {
        "question": "Jelaskan fungsi akar pada tumbuhan bagi kelangsungan hidupnya?",
        "question_type": "esai",
        "answer": "Akar berfungsi menyerap air dan unsur hara dari dalam tanah serta menopang berdirinya tumbuhan.",
    }
    issues = validate_answer_quality(q)
    assert len(issues) == 0
