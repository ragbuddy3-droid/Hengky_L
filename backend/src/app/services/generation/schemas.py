"""Pydantic schemas and dataclasses for Multi-Stage Question Generation."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class _LenientModel(BaseModel):
    """Stage output schema that accepts a list where a text field is expected (some models answer with bullets)."""

    model_config = ConfigDict(extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _join_text_lists(cls, value: Any, info: ValidationInfo) -> Any:
        field = cls.model_fields.get(info.field_name or "")
        if isinstance(value, list) and field is not None and field.annotation in (str, str | None):
            return "; ".join(str(v) for v in value)
        return value


class TestableContentItem(_LenientModel):
    point: str = Field(description="Substansi materi yang dapat diuji")
    source_quote: str = Field(description="Kutipan kalimat persis dari konteks buku")


class ContentAnalysis(_LenientModel):
    """Output of Stage 1 — Context Understanding."""
    topic: str = Field(default="", description="Topik utama materi")
    subtopics: list[str] = Field(default_factory=list, description="Daftar subtopik")
    key_concepts: list[str] = Field(default_factory=list, description="Konsep-konsep penting")
    key_facts: list[str] = Field(default_factory=list, description="Fakta-fakta eksplisit dari konteks")
    relationships: list[str] = Field(default_factory=list, description="Hubungan sebab-akibat atau perbandingan")
    processes: list[str] = Field(default_factory=list, description="Proses atau tahapan jika ada")
    testable_content: list[TestableContentItem] = Field(default_factory=list, description="Poin materi yang dapat diuji")

    model_config = ConfigDict(extra="ignore")


class CognitivePlan(_LenientModel):
    """Output of Stage 2 — Cognitive Bloom Planning."""
    cognitive_level: str = Field(default="C2-Memahami", description="Target level kognitif (C1-C4)")
    cognitive_operation: str = Field(default="", description="Operasi kognitif yang ditargetkan")
    student_task: str = Field(default="", description="Tugas spesifik yang harus dilakukan siswa")
    reasoning_required: str = Field(default="", description="Penalaran yang dibutuhkan siswa")
    stimulus_idea: str | None = Field(default=None, description="Gagasan skenario kontekstual untuk C3/C4")
    expected_evidence: str = Field(default="", description="Bukti pemahaman yang diharapkan")
    recommended_question_format: str = Field(default="esai", description="Format soal (isian_singkat / esai_pendek / esai)")
    prohibited_question_pattern: list[str] = Field(default_factory=list, description="Pola pertanyaan yang dilarang")

    model_config = ConfigDict(extra="ignore")


class QuestionBlueprint(_LenientModel):
    """Output of Stage 3 — Question Blueprint."""
    knowledge_point: str = Field(default="", description="Pokok bahasan spesifik yang diuji")
    question_type: str = Field(default="esai", description="Format soal (isian_singkat / esai)")
    question_intent: str = Field(default="", description="Tujuan/indikator pengukuran siswa")
    grounding_evidence: str = Field(default="", description="Kutipan persis dari teks buku sebagai bukti grounding")
    stimulus_context: str | None = Field(default=None, description="Skenario/cerita kontekstual nyata untuk C3/C4")
    expected_answer_summary: str = Field(default="", description="Ringkasan inti jawaban ideal yang diharapkan")
    answer_scope: str = Field(default="", description="Batasan panjang dan kedalaman jawaban siswa SD")

    model_config = ConfigDict(extra="ignore")


class BatchBlueprint(QuestionBlueprint):
    item: int | None = Field(default=None, description="Nomor butir (1-based) yang dirancang blueprint ini")


class BlueprintBatch(BaseModel):
    """Output of Stage 3 Batch — one blueprint per question of a chunk."""
    blueprints: list[BatchBlueprint] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class QuestionPackage(_LenientModel):
    """Output of Stage 4 — Question Generation Package."""
    question: str = Field(description="Teks pertanyaan untuk siswa SD")
    question_type: str = Field(default="esai", description="Tipe soal (isian_singkat / esai)")
    cognitive_level: str = Field(default="C2-Memahami", description="Tingkat kognitif Bloom")
    knowledge_point: str = Field(default="", description="Pokok materi")
    grounding_evidence: str = Field(default="", description="Kutipan kalimat bukti dari buku")
    expected_answer: str = Field(description="Jawaban ideal yang benar dan konkret")
    explanation: str = Field(default="", description="Penjelasan konteks materi dan alasan jawaban")

    model_config = ConfigDict(extra="ignore")


class JudgeAspectResult(_LenientModel):
    status: str = Field(default="pass", description="pass atau fail")
    score: float | None = Field(default=None, description="Skor numerik jika relevan")
    detected_level: str | None = Field(default=None, description="Level kognitif yang terdeteksi")
    feedback: str = Field(default="", description="Catatan atau masukan evaluasi")


class JudgeEvaluationResult(_LenientModel):
    """Output of LLM-as-Judge Layer 2."""
    grounding: JudgeAspectResult = Field(default_factory=lambda: JudgeAspectResult(status="pass"))
    bloom_adherence: JudgeAspectResult = Field(default_factory=lambda: JudgeAspectResult(status="pass"))
    bahasa: JudgeAspectResult = Field(default_factory=lambda: JudgeAspectResult(status="pass"))
    answerability: JudgeAspectResult = Field(default_factory=lambda: JudgeAspectResult(status="pass"))
    answer_alignment: JudgeAspectResult = Field(default_factory=lambda: JudgeAspectResult(status="pass"))
    overall: str = Field(default="pass", description="pass atau fail")
    failed_stage: str = Field(default="none", description="generation / planning / none")

    model_config = ConfigDict(extra="ignore")


class PromptStageTrace(BaseModel):
    """Jejak eksekusi prompt untuk audit dan inspeksi."""
    stage_name: str = Field(description="Nama tahap (Stage 1, Stage 2, Stage 3, Stage 4, Judge, Refinement A, Refinement B)")
    step_number: int = Field(default=1, description="Nomor urutan tahap")
    attempt_number: int = Field(default=1, description="Nomor iterasi percobaan")
    prompt_sent: str = Field(description="Teks prompt lengkap yang dikirim ke LLM")
    raw_response: str = Field(description="Respons mentah yang dikembalikan oleh LLM")
    parsed_output: dict[str, Any] = Field(default_factory=dict, description="Hasil data terstruktur (JSON)")
    latency_ms: int = Field(default=0, description="Durasi eksekusi dalam milidetik")
    status: str = Field(default="success", description="success / error / fallback")
    error_message: str | None = Field(default=None, description="Pesan error jika ada")
    has_fallback: bool = Field(default=False, description="True jika output menggunakan data fallback/dummy")
