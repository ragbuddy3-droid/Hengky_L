"""Async stage runners for the Multi-Stage AQG prompts: every stage shares one invoke -> parse -> trace path."""

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.generation.planner import NO_FEW_SHOT, normalize_bloom_level
from app.services.generation.prompts import (
    LLM_JUDGE_PROMPT,
    REFINEMENT_PROMPT_A,
    REFINEMENT_PROMPT_B,
    STAGE1_CONTEXT_UNDERSTANDING_PROMPT,
    STAGE2_COGNITIVE_PLANNING_PROMPT,
    STAGE3_BATCH_BLUEPRINT_PROMPT,
    STAGE3_QUESTION_BLUEPRINT_PROMPT,
    STAGE4_QUESTION_GENERATION_PROMPT,
    SYSTEM_ANALYSIS_PERSONA,
    SYSTEM_DESIGNER_PERSONA,
    SYSTEM_GENERATOR_PERSONA,
    SYSTEM_JUDGE_PERSONA,
    SYSTEM_REFINEMENT_PERSONA,
)
from app.services.generation.schemas import (
    BlueprintBatch,
    CognitivePlan,
    ContentAnalysis,
    JudgeAspectResult,
    JudgeEvaluationResult,
    PromptStageTrace,
    QuestionBlueprint,
    QuestionPackage,
    TestableContentItem,
)
from app.services.llm import get_chat_model

logger = logging.getLogger(__name__)

# The judge sees the same material the generator used: the question's own chunk (~1000 chars with fixed chunking).
JUDGE_CONTEXT_CHARS = 1500

T = TypeVar("T", bound=BaseModel)


# ── Text Cleaning & JSON Extraction Helpers ──

def strip_reasoning_tags(text: str) -> str:
    """Remove <think>...</think> and unclosed reasoning tags from model response."""
    if not text:
        return ""
    cleaned = re.sub(r'<(think|thought)>[\s\S]*?</\1>', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'<(think|thought)>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_json_string(s: str) -> str:
    """Strip markdown fences and trailing commas before closing braces/brackets."""
    if not s:
        return ""
    s = re.sub(r'^```(?:json)?\s*', '', s.strip(), flags=re.IGNORECASE)
    s = re.sub(r'\s*```$', '', s.strip(), flags=re.IGNORECASE)
    s = re.sub(r',\s*([\]}])', r'\1', s)
    return s.strip()


def _try_load_dict(text: str) -> dict[str, Any] | None:
    try:
        res = json.loads(clean_json_string(text), strict=False)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return res if isinstance(res, dict) else None


def extract_json_object(response_text: str) -> dict[str, Any]:
    """Robust multi-tier JSON parser for single object model responses."""
    if not response_text:
        return {}
    text = strip_reasoning_tags(response_text) or response_text

    # Tier 1: Markdown code blocks ```json ... ```
    for block in re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE):
        if (res := _try_load_dict(block)) is not None:
            return res

    # Tier 2: Outer brace search {...}
    first, last = text.find('{'), text.rfind('}')
    if first != -1 and last > first and (res := _try_load_dict(text[first:last + 1])) is not None:
        return res

    # Tier 3: Loose JSON regex match
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text):
        if (res := _try_load_dict(m.group(0))) is not None:
            return res

    return {}


def invoke_json(system: str, prompt: str, temperature: float) -> dict[str, Any]:
    """One blocking JSON-mode call to the generator model; returns the parsed object ({} if none)."""
    resp = get_chat_model(temperature=temperature).invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    return extract_json_object(raw)


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


# ── Generic Stage Execution ──

_llm_slots: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None


def _llm_semaphore() -> asyncio.Semaphore:
    """Process-wide cap on LLM calls in flight (generation, judge and refinement share it)."""
    global _llm_slots
    loop = asyncio.get_running_loop()
    if _llm_slots is None or _llm_slots[0] is not loop:
        _llm_slots = (loop, asyncio.Semaphore(get_settings().generation.concurrency))
    return _llm_slots[1]


async def _run_stage(
    chat_model: Any,
    persona: str,
    prompt_text: str,
    schema: type[T],
    stage_name: str,
    step_number: int,
    attempt: int,
    fallback: Callable[[], T],
    error_status: str = "fallback",
) -> tuple[T, PromptStageTrace]:
    """Invoke the model, parse its JSON into `schema`, and record a trace; use `fallback()` on any failure."""
    t0 = time.perf_counter()
    raw_response = ""
    status = "success"
    err_msg = None

    try:
        async with _llm_semaphore():
            resp = await chat_model.ainvoke([SystemMessage(content=persona), HumanMessage(content=prompt_text)])
        raw_response = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed_obj = schema.model_validate(extract_json_object(raw_response))
    except Exception as e:
        logger.error("[%s] Error: %s", stage_name, e)
        status = error_status
        err_msg = str(e)
        parsed_obj = fallback()

    trace = PromptStageTrace(
        stage_name=stage_name,
        step_number=step_number,
        attempt_number=attempt,
        prompt_sent=prompt_text,
        raw_response=raw_response,
        parsed_output=parsed_obj.model_dump(),
        latency_ms=int((time.perf_counter() - t0) * 1000),
        status=status,
        error_message=err_msg,
        has_fallback=(status == "fallback"),
    )
    return parsed_obj, trace


# ── Stage Runners ──

async def run_stage1_context_understanding(
    chat_model: Any,
    retrieved_context: str,
    attempt: int = 1,
) -> tuple[ContentAnalysis, PromptStageTrace]:
    """Stage 1: Context Understanding (one call per chunk)."""
    return await _run_stage(
        chat_model,
        SYSTEM_ANALYSIS_PERSONA,
        STAGE1_CONTEXT_UNDERSTANDING_PROMPT.format(retrieved_context=retrieved_context),
        ContentAnalysis,
        "Stage 1: Context Understanding",
        1,
        attempt,
        lambda: ContentAnalysis(
            topic="Materi Pembelajaran",
            testable_content=[TestableContentItem(point="Konsep dasar", source_quote=retrieved_context[:200])],
        ),
    )


async def run_stage2_cognitive_planning(
    chat_model: Any,
    content_analysis: ContentAnalysis,
    target_bloom_level: str,
    attempt: int = 1,
) -> tuple[CognitivePlan, PromptStageTrace]:
    """Stage 2: Cognitive Bloom Planning (C1-C4 only)."""
    clean_bloom = normalize_bloom_level(target_bloom_level) or "C2-Memahami"
    return await _run_stage(
        chat_model,
        SYSTEM_DESIGNER_PERSONA,
        STAGE2_COGNITIVE_PLANNING_PROMPT.format(
            target_bloom_level=clean_bloom,
            content_analysis=_compact_content_analysis(content_analysis),
        ),
        CognitivePlan,
        "Stage 2: Cognitive Bloom Planning",
        2,
        attempt,
        lambda: CognitivePlan(
            cognitive_level=clean_bloom,
            cognitive_operation="Memahami dan menjelaskan konsep utama",
            student_task="Menjelaskan konsep sesuai isi teks buku",
            reasoning_required="Pemahaman makna istilah/konsep",
            expected_evidence="Menyebutkan poin-poin penjelasan",
            recommended_question_format="esai",
            prohibited_question_pattern=["Apa yang kamu rasakan", "Apa tujuan pembelajaran"],
        ),
    )


def _fallback_blueprint(point: str, quote: str, plan: CognitivePlan) -> QuestionBlueprint:
    return QuestionBlueprint(
        knowledge_point=point or "Materi Pokok",
        question_type=plan.recommended_question_format or "esai",
        question_intent=plan.student_task or "Menguji pemahaman materi",
        grounding_evidence=quote,
        expected_answer_summary=quote,
        answer_scope="1-2 kalimat sederhana",
    )


async def run_stage3_question_blueprint(
    chat_model: Any,
    content_analysis: ContentAnalysis,
    cognitive_plan: CognitivePlan,
    focus_knowledge_point: str | None = None,
    attempt: int = 1,
) -> tuple[QuestionBlueprint, PromptStageTrace]:
    """Stage 3: Question Blueprint for one knowledge point (used when refinement re-plans a single question)."""
    prompt_text = STAGE3_QUESTION_BLUEPRINT_PROMPT.format(
        content_analysis=_compact_content_analysis(content_analysis),
        cognitive_plan=json.dumps(cognitive_plan.model_dump(), ensure_ascii=False),
    )
    if focus_knowledge_point:
        prompt_text += f"\n\nCATATAN KHUSUS: Rancang blueprint ini KHUSUS menguji poin materi berikut: '{focus_knowledge_point}'."

    def fallback() -> QuestionBlueprint:
        quote = ""
        if content_analysis.testable_content:
            quote = content_analysis.testable_content[0].source_quote
        elif content_analysis.key_facts:
            quote = content_analysis.key_facts[0]
        return _fallback_blueprint(focus_knowledge_point or content_analysis.topic, quote, cognitive_plan)

    return await _run_stage(
        chat_model, SYSTEM_DESIGNER_PERSONA, prompt_text, QuestionBlueprint,
        "Stage 3: Question Blueprint", 3, attempt, fallback,
    )


async def run_stage3_blueprint_batch(
    chat_model: Any,
    chunk_text: str,
    items: list[dict[str, Any]],
    plans: dict[str, CognitivePlan],
    attempt: int = 1,
) -> tuple[list[QuestionBlueprint], list[bool], PromptStageTrace]:
    """Stage 3 Batch: blueprints for all questions of one chunk in a single call.

    `items` carry "point", "quote", and "bloom_level". Seeing its siblings lets the model give every
    question a different angle. Returns (blueprints aligned with items, per-item fallback flags, trace);
    an item the model skipped gets a fallback blueprint built from its own quote.
    """
    levels = list(dict.fromkeys(it["bloom_level"] for it in items))
    item_lines = "\n".join(
        f"{n}. poin: {it['point']}\n   kutipan: {it.get('quote', '')}\n   level: {it['bloom_level']}"
        for n, it in enumerate(items, 1)
    )
    prompt_text = STAGE3_BATCH_BLUEPRINT_PROMPT.format(
        chunk_text=chunk_text,
        cognitive_plans=json.dumps({lvl: plans[lvl].model_dump() for lvl in levels}, ensure_ascii=False),
        items=item_lines,
    )
    batch, trace = await _run_stage(
        chat_model, SYSTEM_DESIGNER_PERSONA, prompt_text, BlueprintBatch,
        "Stage 3: Question Blueprint (batch per chunk)", 3, attempt, BlueprintBatch,
    )

    by_item = {bp.item: bp for bp in batch.blueprints if bp.item is not None}
    use_numbers = len(by_item) == len(batch.blueprints) and set(by_item) <= set(range(1, len(items) + 1))
    blueprints: list[QuestionBlueprint] = []
    fallbacks: list[bool] = []
    for n, it in enumerate(items, 1):
        bp = by_item.get(n) if use_numbers else (batch.blueprints[n - 1] if n <= len(batch.blueprints) else None)
        if bp is None:
            blueprints.append(_fallback_blueprint(it["point"], it.get("quote", ""), plans[it["bloom_level"]]))
            fallbacks.append(True)
        else:
            blueprints.append(QuestionBlueprint.model_validate(bp.model_dump(exclude={"item"})))
            fallbacks.append(False)
    return blueprints, fallbacks, trace


async def run_stage4_question_generation(
    chat_model: Any,
    retrieved_context: str,
    blueprint: QuestionBlueprint,
    target_bloom_level: str,
    question_type: str = "esai",
    few_shot_examples: str = NO_FEW_SHOT,
    attempt: int = 1,
) -> tuple[QuestionPackage, PromptStageTrace]:
    """Stage 4: Question Generation (Question + Answer + Explanation)."""
    return await _run_stage(
        chat_model,
        SYSTEM_GENERATOR_PERSONA,
        STAGE4_QUESTION_GENERATION_PROMPT.format(
            retrieved_context=retrieved_context,
            question_blueprint=json.dumps(blueprint.model_dump(), ensure_ascii=False),
            few_shot_examples=few_shot_examples or NO_FEW_SHOT,
            question_type=question_type,
            target_bloom_level=target_bloom_level,
        ),
        QuestionPackage,
        "Stage 4: Question Generation",
        4,
        attempt,
        lambda: QuestionPackage(
            question=f"Jelaskan {blueprint.knowledge_point} berdasarkan materi yang dipelajari!",
            question_type=question_type,
            cognitive_level=target_bloom_level,
            knowledge_point=blueprint.knowledge_point,
            grounding_evidence=blueprint.grounding_evidence,
            expected_answer=blueprint.grounding_evidence or "Jawaban sesuai materi buku.",
            explanation=f"Materi ini merujuk pada konsep '{blueprint.knowledge_point}' dalam buku.",
        ),
    )


async def run_llm_judge(
    judge_model: Any,
    retrieved_context: str,
    grounding_evidence: str,
    question: str,
    expected_answer: str,
    explanation: str,
    target_bloom_level: str,
    attempt: int = 1,
) -> tuple[JudgeEvaluationResult, PromptStageTrace]:
    """Layer 2: LLM-as-Judge evaluation. A failed call counts as a failed evaluation, not a pass."""

    def fallback() -> JudgeEvaluationResult:
        failed = JudgeAspectResult(status="fail", feedback="Evaluasi gagal.")
        return JudgeEvaluationResult(
            grounding=failed,
            bloom_adherence=JudgeAspectResult(status="fail", detected_level="unknown", feedback="Evaluasi gagal."),
            bahasa=failed,
            answerability=failed,
            answer_alignment=failed,
            overall="fail",
            failed_stage="generation",
        )

    return await _run_stage(
        judge_model,
        SYSTEM_JUDGE_PERSONA,
        LLM_JUDGE_PROMPT.format(
            retrieved_context=retrieved_context[:JUDGE_CONTEXT_CHARS],
            grounding_evidence=grounding_evidence or "Teks konteks buku",
            question=question,
            expected_answer=expected_answer,
            explanation=explanation or f"Berdasarkan materi '{grounding_evidence}'.",
            target_bloom_level=target_bloom_level,
        ),
        JudgeEvaluationResult,
        "Layer 2: LLM-as-Judge",
        5,
        attempt,
        fallback,
        error_status="error",
    )


async def run_refinement_a(
    chat_model: Any,
    question: str,
    expected_answer: str,
    explanation: str,
    blueprint: QuestionBlueprint,
    retrieved_context: str,
    validation_feedback: str,
    target_bloom_level: str,
    question_type: str = "esai",
    attempt: int = 2,
) -> tuple[QuestionPackage, PromptStageTrace]:
    """Refinement Prompt A (Generation-level repair, Stage 4 re-entry)."""
    return await _run_stage(
        chat_model,
        SYSTEM_REFINEMENT_PERSONA,
        REFINEMENT_PROMPT_A.format(
            question=question,
            expected_answer=expected_answer,
            explanation=explanation or "Penjelasan sesuai materi.",
            question_blueprint=json.dumps(blueprint.model_dump(), ensure_ascii=False),
            retrieved_context=retrieved_context,
            validation_feedback=validation_feedback,
            question_type=question_type,
            target_bloom_level=target_bloom_level,
        ),
        QuestionPackage,
        "Refinement Prompt A (Generation Repair)",
        6,
        attempt,
        lambda: QuestionPackage(
            question=question,
            question_type=question_type,
            cognitive_level=target_bloom_level,
            knowledge_point=blueprint.knowledge_point,
            grounding_evidence=blueprint.grounding_evidence,
            expected_answer=expected_answer,
            explanation=explanation or "Penjelasan sesuai materi.",
        ),
    )


async def run_refinement_b(
    chat_model: Any,
    prev_plan: CognitivePlan,
    question_text: str,
    validation_feedback: str,
    detected_level: str,
    target_bloom_level: str,
    content_analysis: ContentAnalysis,
    attempt: int = 2,
) -> tuple[CognitivePlan, PromptStageTrace]:
    """Refinement Prompt B (Planning-level repair, Stage 2-3 re-entry)."""
    return await _run_stage(
        chat_model,
        SYSTEM_REFINEMENT_PERSONA,
        REFINEMENT_PROMPT_B.format(
            cognitive_plan=json.dumps(prev_plan.model_dump(), ensure_ascii=False),
            question=question_text,
            validation_feedback=validation_feedback,
            detected_level=detected_level or "Tidak sesuai",
            target_bloom_level=target_bloom_level,
            content_analysis=_compact_content_analysis(content_analysis),
        ),
        CognitivePlan,
        "Refinement Prompt B (Cognitive Planning Redesign)",
        6,
        attempt,
        lambda: prev_plan,
    )
