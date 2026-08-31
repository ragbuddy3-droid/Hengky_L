"""Stage runners for executing Multi-Stage AQG prompt templates with robust parsing and tracing."""

import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.generation.prompts import (
    LLM_JUDGE_PROMPT,
    REFINEMENT_PROMPT_A,
    REFINEMENT_PROMPT_B,
    STAGE1_CONTEXT_UNDERSTANDING_PROMPT,
    STAGE2_COGNITIVE_PLANNING_PROMPT,
    STAGE3_QUESTION_BLUEPRINT_PROMPT,
    STAGE4_QUESTION_GENERATION_PROMPT,
    SYSTEM_ANALYSIS_PERSONA,
    SYSTEM_DESIGNER_PERSONA,
    SYSTEM_GENERATOR_PERSONA,
    SYSTEM_JUDGE_PERSONA,
    SYSTEM_REFINEMENT_PERSONA,
)
from app.services.generation.schemas import (
    CognitivePlan,
    ContentAnalysis,
    JudgeAspectResult,
    JudgeEvaluationResult,
    PromptStageTrace,
    QuestionBlueprint,
    QuestionPackage,
)

logger = logging.getLogger(__name__)


# ── Text Cleaning & JSON Extraction Helpers ──

def strip_reasoning_tags(text: str) -> str:
    """Remove <think>...</think> and unclosed reasoning tags from model response."""
    if not text:
        return ""
    cleaned = re.sub(r'<(think|thought)>[\s\S]*?</\1>', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'<(think|thought)>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_json_string(s: str) -> str:
    """Clean trailing commas before closing braces/brackets and fix common syntax issues."""
    if not s:
        return ""
    # Strip markdown codeblocks markers if passed directly
    s = re.sub(r'^```(?:json)?\s*', '', s.strip(), flags=re.IGNORECASE)
    s = re.sub(r'\s*```$', '', s.strip(), flags=re.IGNORECASE)
    # Remove trailing commas before closing braces or brackets
    s = re.sub(r',\s*([\]}])', r'\1', s)
    return s.strip()


def extract_json_object(response_text: str) -> dict[str, Any]:
    """Robust multi-tier JSON parser for single object model responses."""
    if not response_text:
        return {}

    cleaned = strip_reasoning_tags(response_text)
    text_to_search = cleaned if cleaned else response_text

    # Tier 1: Markdown code blocks ```json ... ```
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text_to_search, re.IGNORECASE)
    for block in code_blocks:
        b_clean = clean_json_string(block.strip())
        try:
            res = json.loads(b_clean, strict=False)
            if isinstance(res, dict):
                return res
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Tier 2: Outer brace search {...}
    first_brace = text_to_search.find('{')
    last_brace = text_to_search.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        sub = clean_json_string(text_to_search[first_brace:last_brace + 1])
        try:
            res = json.loads(sub, strict=False)
            if isinstance(res, dict):
                return res
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Tier 3: Loose JSON regex match
    pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    for m in re.finditer(pattern, text_to_search):
        try:
            res = json.loads(clean_json_string(m.group(0)), strict=False)
            if isinstance(res, dict):
                return res
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return {}


def _compact_content_analysis(ca: ContentAnalysis) -> str:
    """Token-efficient serialization of ContentAnalysis for downstream prompts."""
    pruned = {
        "topic": ca.topic,
        "key_concepts": ca.key_concepts[:5],
        "key_facts": ca.key_facts[:5],
        "testable_content": [
            {"point": tc.point, "source_quote": tc.source_quote[:150]}
            for tc in ca.testable_content[:6]
        ],
    }
    return json.dumps(pruned, ensure_ascii=False)


# ── Stage Runners ──

def run_stage1_context_understanding(
    chat_model: Any,
    retrieved_context: str,
    attempt: int = 1
) -> tuple[ContentAnalysis, PromptStageTrace]:
    """Stage 1: Execute Context Understanding Prompt."""
    prompt_text = STAGE1_CONTEXT_UNDERSTANDING_PROMPT.format(
        retrieved_context=retrieved_context
    )

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_ANALYSIS_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = ContentAnalysis.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[Stage 1 Runner] Error: %s", e)
        status = "fallback"
        err_msg = str(e)
        parsed_dict = {
            "topic": "Materi Pembelajaran",
            "subtopics": [],
            "key_concepts": [],
            "key_facts": [],
            "testable_content": [{"point": "Konsep dasar", "source_quote": retrieved_context[:200]}]
        }
        parsed_obj = ContentAnalysis.model_validate(parsed_dict)

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Stage 1: Context Understanding",
        step_number=1,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


def run_stage2_cognitive_planning(
    chat_model: Any,
    content_analysis: ContentAnalysis,
    target_bloom_level: str,
    attempt: int = 1
) -> tuple[CognitivePlan, PromptStageTrace]:
    """Stage 2: Execute Cognitive Bloom Planning Prompt (C1-C4 only)."""
    clean_bloom = (
        target_bloom_level
        if target_bloom_level in [
            "C1", "C2", "C3", "C4",
            "C1-Mengingat", "C2-Memahami", "C3-Menerapkan",
            "C4-Menganalisis", "C3-Mengaplikasikan",
        ]
        else "C2-Memahami"
    )

    prompt_text = STAGE2_COGNITIVE_PLANNING_PROMPT.format(
        target_bloom_level=clean_bloom,
        content_analysis=_compact_content_analysis(content_analysis)
    )

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_DESIGNER_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = CognitivePlan.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[Stage 2 Runner] Error: %s", e)
        status = "fallback"
        err_msg = str(e)
        parsed_dict = {
            "cognitive_level": clean_bloom,
            "cognitive_operation": "Memahami dan menjelaskan konsep utama",
            "student_task": "Menjelaskan konsep sesuai isi teks buku",
            "reasoning_required": "Pemahaman makna istilah/konsep",
            "expected_evidence": "Menyebutkan poin-poin penjelasan",
            "recommended_question_format": "esai",
            "prohibited_question_pattern": ["Apa yang kamu rasakan", "Apa tujuan pembelajaran"]
        }
        parsed_obj = CognitivePlan.model_validate(parsed_dict)

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Stage 2: Cognitive Bloom Planning",
        step_number=2,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


def run_stage3_question_blueprint(
    chat_model: Any,
    content_analysis: ContentAnalysis,
    cognitive_plan: CognitivePlan,
    focus_knowledge_point: str | None = None,
    attempt: int = 1
) -> tuple[QuestionBlueprint, PromptStageTrace]:
    """Stage 3: Execute Question Blueprint Prompt with optional target knowledge point focus."""
    compact_ca_str = _compact_content_analysis(content_analysis)

    prompt_text = STAGE3_QUESTION_BLUEPRINT_PROMPT.format(
        content_analysis=compact_ca_str,
        cognitive_plan=json.dumps(cognitive_plan.model_dump(), ensure_ascii=False)
    )
    if focus_knowledge_point:
        prompt_text += f"\n\nCATATAN KHUSUS: Rancang blueprint ini KHUSUS menguji poin materi berikut: '{focus_knowledge_point}'."

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_DESIGNER_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = QuestionBlueprint.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[Stage 3 Runner] Error: %s", e)
        status = "fallback"
        err_msg = str(e)
        quote = ""
        if content_analysis.testable_content:
            quote = content_analysis.testable_content[0].source_quote
        elif content_analysis.key_facts:
            quote = content_analysis.key_facts[0]

        parsed_dict = {
            "knowledge_point": focus_knowledge_point or content_analysis.topic or "Materi Pokok",
            "question_type": cognitive_plan.recommended_question_format or "esai",
            "question_intent": cognitive_plan.student_task or "Menguji pemahaman materi",
            "grounding_evidence": quote,
            "expected_answer_summary": quote,
            "answer_scope": "1-2 kalimat sederhana"
        }
        parsed_obj = QuestionBlueprint.model_validate(parsed_dict)

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Stage 3: Question Blueprint",
        step_number=3,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


def run_stage4_question_generation(
    chat_model: Any,
    retrieved_context: str,
    blueprint: QuestionBlueprint,
    target_bloom_level: str,
    question_type: str = "esai",
    few_shot_examples: str = "Tidak ada contoh tambahan.",
    attempt: int = 1
) -> tuple[QuestionPackage, PromptStageTrace]:
    """Stage 4: Execute Question Generation Prompt (Question + Answer + Explanation)."""
    prompt_text = STAGE4_QUESTION_GENERATION_PROMPT.format(
        retrieved_context=retrieved_context,
        question_blueprint=json.dumps(blueprint.model_dump(), ensure_ascii=False),
        few_shot_examples=few_shot_examples or "Tidak ada contoh tambahan.",
        question_type=question_type,
        target_bloom_level=target_bloom_level
    )

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_GENERATOR_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = QuestionPackage.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[Stage 4 Runner] Error: %s", e)
        status = "fallback"
        err_msg = str(e)
        parsed_dict = {
            "question": f"Jelaskan {blueprint.knowledge_point} berdasarkan materi yang dipelajari!",
            "question_type": question_type,
            "cognitive_level": target_bloom_level,
            "knowledge_point": blueprint.knowledge_point,
            "grounding_evidence": blueprint.grounding_evidence,
            "expected_answer": blueprint.grounding_evidence or "Jawaban sesuai materi buku.",
            "explanation": f"Materi ini merujuk pada konsep '{blueprint.knowledge_point}' dalam buku."
        }
        parsed_obj = QuestionPackage.model_validate(parsed_dict)

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Stage 4: Question Generation",
        step_number=4,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


def run_llm_judge(
    judge_model: Any,
    retrieved_context: str,
    grounding_evidence: str,
    question: str,
    expected_answer: str,
    explanation: str,
    target_bloom_level: str,
    attempt: int = 1
) -> tuple[JudgeEvaluationResult, PromptStageTrace]:
    """Layer 2: Execute LLM-as-Judge Evaluation (Streamlined: Question + Answer + Explanation)."""
    prompt_text = LLM_JUDGE_PROMPT.format(
        retrieved_context=retrieved_context[:2000],
        grounding_evidence=grounding_evidence or "Teks konteks buku",
        question=question,
        expected_answer=expected_answer,
        explanation=explanation or f"Berdasarkan materi '{grounding_evidence}'.",
        target_bloom_level=target_bloom_level
    )

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = judge_model.invoke([
            SystemMessage(content=SYSTEM_JUDGE_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = JudgeEvaluationResult.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[LLM Judge Runner] Error: %s", e)
        status = "error"
        err_msg = str(e)
        parsed_obj = JudgeEvaluationResult(
            grounding=JudgeAspectResult(status="fail", feedback=f"Evaluasi gagal: {e}"),
            bloom_adherence=JudgeAspectResult(status="fail", detected_level="unknown", feedback="Evaluasi gagal."),
            bahasa=JudgeAspectResult(status="fail", feedback="Evaluasi gagal."),
            answerability=JudgeAspectResult(status="fail", feedback="Evaluasi gagal."),
            answer_alignment=JudgeAspectResult(status="fail", feedback="Evaluasi gagal."),
            overall="fail",
            failed_stage="generation"
        )

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Layer 2: LLM-as-Judge",
        step_number=5,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


def run_refinement_a(
    chat_model: Any,
    question: str,
    expected_answer: str,
    explanation: str,
    blueprint: QuestionBlueprint,
    retrieved_context: str,
    validation_feedback: str,
    target_bloom_level: str,
    question_type: str = "esai",
    attempt: int = 2
) -> tuple[QuestionPackage, PromptStageTrace]:
    """Refinement Prompt A (Generation-level repair, Stage 4 re-entry)."""
    prompt_text = REFINEMENT_PROMPT_A.format(
        question=question,
        expected_answer=expected_answer,
        explanation=explanation or "Penjelasan sesuai materi.",
        question_blueprint=json.dumps(blueprint.model_dump(), ensure_ascii=False),
        retrieved_context=retrieved_context,
        validation_feedback=validation_feedback,
        question_type=question_type,
        target_bloom_level=target_bloom_level
    )

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_REFINEMENT_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = QuestionPackage.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[Refinement A Runner] Error: %s", e)
        status = "fallback"
        err_msg = str(e)
        parsed_obj = QuestionPackage(
            question=question,
            question_type=question_type,
            cognitive_level=target_bloom_level,
            knowledge_point=blueprint.knowledge_point,
            grounding_evidence=blueprint.grounding_evidence,
            expected_answer=expected_answer,
            explanation=explanation or "Penjelasan sesuai materi."
        )

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Refinement Prompt A (Generation Repair)",
        step_number=6,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


def run_refinement_b(
    chat_model: Any,
    prev_plan: CognitivePlan,
    question_text: str,
    validation_feedback: str,
    detected_level: str,
    target_bloom_level: str,
    content_analysis: ContentAnalysis,
    attempt: int = 2
) -> tuple[CognitivePlan, PromptStageTrace]:
    """Refinement Prompt B (Planning-level repair, Stage 2-3 re-entry)."""
    compact_ca_str = _compact_content_analysis(content_analysis)

    prompt_text = REFINEMENT_PROMPT_B.format(
        cognitive_plan=json.dumps(prev_plan.model_dump(), ensure_ascii=False),
        question=question_text,
        validation_feedback=validation_feedback,
        detected_level=detected_level or "Tidak sesuai",
        target_bloom_level=target_bloom_level,
        content_analysis=compact_ca_str
    )

    t0 = time.time()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_REFINEMENT_PERSONA),
            HumanMessage(content=prompt_text),
        ])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_dict = extract_json_object(raw_response)
        parsed_obj = CognitivePlan.model_validate(parsed_dict)
    except Exception as e:
        logger.error("[Refinement B Runner] Error: %s", e)
        status = "fallback"
        err_msg = str(e)
        parsed_obj = prev_plan

    latency = int((time.time() - t0) * 1000)
    trace = PromptStageTrace(
        stage_name="Refinement Prompt B (Cognitive Planning Redesign)",
        step_number=6,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=latency,
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace
