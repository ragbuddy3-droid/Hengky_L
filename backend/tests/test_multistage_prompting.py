"""Unit tests for Multi-Stage AQG prompting pipeline, stage schemas, and grounding checker."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.generation.schemas import (
    CognitivePlan,
    ContentAnalysis,
    JudgeEvaluationResult,
    QuestionBlueprint,
    QuestionPackage,
)
from app.services.generation.stage_runners import (
    extract_json_object,
    strip_reasoning_tags,
)

client = TestClient(app)


def test_strip_reasoning_tags():
    """Verify <think> and <thought> tags are properly stripped."""
    text_with_think = "<think>Ini adalah penalaran internal model</think>{\"topic\": \"Pencernaan\"}"
    cleaned = strip_reasoning_tags(text_with_think)
    assert cleaned == '{"topic": "Pencernaan"}'

    unclosed_think = "<thought>Penalaran tanpa penutup"
    cleaned_unclosed = strip_reasoning_tags(unclosed_think)
    assert cleaned_unclosed == ""


def test_extract_json_object():
    """Verify robust JSON extraction across markdown codeblocks, braces, and trailing commas."""
    markdown_json = "Berikut output JSON:\n```json\n{\n  \"topic\": \"Pernapasan\",\n  \"key_concepts\": [\"Paru-paru\", \"Hidung\",]\n}\n```"
    parsed = extract_json_object(markdown_json)
    assert parsed.get("topic") == "Pernapasan"
    assert "Paru-paru" in parsed.get("key_concepts", [])

    raw_brace_json = "Tentu! {\"score\": 2, \"criteria\": \"Menjelaskan lengkap\"} Terima kasih."
    parsed2 = extract_json_object(raw_brace_json)
    assert parsed2.get("score") == 2


def test_stage1_content_analysis_schema():
    """Verify Stage 1 ContentAnalysis Pydantic schema validation."""
    data = {
        "topic": "Sistem Peredaran Darah",
        "subtopics": ["Jantung", "Pembuluh Darah"],
        "key_concepts": ["Darah bersih", "Darah kotor", "Ventrikel"],
        "key_facts": ["Jantung memompa darah ke seluruh tubuh."],
        "relationships": ["Arteri membawa darah kaya oksigen."],
        "processes": ["Darah masuk ke serambi kanan lalu ke bilik kanan."],
        "testable_content": [
            {
                "point": "Fungsi jantung manusia",
                "source_quote": "Jantung memompa darah ke seluruh tubuh."
            }
        ]
    }
    obj = ContentAnalysis.model_validate(data)
    assert obj.topic == "Sistem Peredaran Darah"
    assert len(obj.testable_content) == 1
    assert obj.testable_content[0].source_quote == "Jantung memompa darah ke seluruh tubuh."


def test_stage2_cognitive_plan_schema():
    """Verify Stage 2 CognitivePlan Pydantic schema validation."""
    data = {
        "cognitive_level": "C2-Memahami",
        "cognitive_operation": "Menjelaskan fungsi organ dengan kata-kata sendiri",
        "student_task": "Menjelaskan cara kerja jantung dalam peredaran darah",
        "reasoning_required": "Pemahaman alur darah kaya oksigen",
        "expected_evidence": "Menyebutkan bilik jantung dan arah aliran darah",
        "recommended_question_format": "esai",
        "prohibited_question_pattern": ["Apa yang sudah kamu pelajari"]
    }
    obj = CognitivePlan.model_validate(data)
    assert obj.cognitive_level == "C2-Memahami"
    assert obj.recommended_question_format == "esai"
    assert len(obj.prohibited_question_pattern) == 1


def test_stage3_question_blueprint_schema():
    """Verify Stage 3 QuestionBlueprint schema validation."""
    data = {
        "knowledge_point": "Fungsi bilik kiri jantung",
        "question_type": "esai",
        "question_intent": "Mengukur pemahaman fungsi bilik kiri memompa darah ke seluruh tubuh",
        "grounding_evidence": "Bilik kiri bertugas memompa darah bersih ke seluruh tubuh.",
        "expected_answer_summary": "Bilik kiri memompa darah bersih/kaya oksigen ke seluruh tubuh.",
        "answer_scope": "1-2 kalimat untuk siswa SD kelas 5",
    }
    obj = QuestionBlueprint.model_validate(data)
    assert obj.knowledge_point == "Fungsi bilik kiri jantung"
    assert "seluruh tubuh" in obj.grounding_evidence
    assert "Bilik kiri" in obj.expected_answer_summary


def test_stage4_question_package_schema():
    """Verify Stage 4 QuestionPackage schema with explanation validation."""
    data = {
        "question": "Jelaskan fungsi dari bilik kiri pada jantung manusia!",
        "question_type": "esai",
        "cognitive_level": "C2-Memahami",
        "knowledge_point": "Fungsi bilik kiri",
        "grounding_evidence": "Bilik kiri bertugas memompa darah bersih ke seluruh tubuh.",
        "expected_answer": "Bilik kiri berfungsi untuk memompa darah bersih yang kaya oksigen ke seluruh tubuh.",
        "explanation": "Jantung memiliki 4 ruang, di mana bilik kiri khusus memompa darah bersih ke seluruh organ tubuh."
    }
    obj = QuestionPackage.model_validate(data)
    assert obj.question.startswith("Jelaskan")
    assert "bilik kiri" in obj.explanation
    assert len(obj.rubric) == 0


def test_llm_judge_evaluation_schema():
    """Verify LLM-as-Judge evaluation schema."""
    data = {
        "grounding": {"status": "pass", "score": 0.95, "feedback": "Didukung teks."},
        "bloom_adherence": {"status": "pass", "detected_level": "C2-Memahami", "feedback": "Sesuai level C2."},
        "bahasa": {"status": "pass", "feedback": "Bahasa sederhana untuk SD."},
        "answerability": {"status": "pass", "feedback": "Dapat dijawab dari konteks."},
        "answer_alignment": {"status": "pass", "feedback": "Jawaban dan penjelasan relevan."},
        "overall": "pass",
        "failed_stage": "none"
    }
    obj = JudgeEvaluationResult.model_validate(data)
    assert obj.overall == "pass"
    assert obj.failed_stage == "none"
    assert obj.bloom_adherence.detected_level == "C2-Memahami"


def test_api_question_detail_multi_stage_schema():
    """Verify questions list and detail endpoints return multi-stage response structure."""
    res = client.get("/api/v1/questions/")
    assert res.status_code == 200
    questions = res.json()
    assert isinstance(questions, list)


def test_generation_intent_detection():
    """Verify natural language question generation intent detection."""
    from app.api.v1.chat import _parse_generation_params, is_generation_intent

    # Variations of user generation requests
    req1 = "Buatkan 3 soal esai C2 Bab 3 Jejak Sang Pahlawan, Daerahku di Masa Penjajahan"
    assert is_generation_intent(req1) is True
    p1 = _parse_generation_params(req1)
    assert p1.num_questions == 3
    assert p1.bloom_level == "C2-Memahami"
    assert p1.chapter == "3"

    req2 = "Tolong buatkan 5 soal C4 bab 2"
    assert is_generation_intent(req2) is True
    p2 = _parse_generation_params(req2)
    assert p2.num_questions == 5
    assert p2.bloom_level == "C4-Menganalisis"
    assert p2.chapter == "2"

    req3 = "Bikin 2 pertanyaan isian singkat materi hidung"
    assert is_generation_intent(req3) is True
    p3 = _parse_generation_params(req3)
    assert p3.num_questions == 2

    # Conversational messages
    assert is_generation_intent("Halo apa kabar?") is False
    assert is_generation_intent("Terima kasih banyak atas bantuannya") is False

