"""LangGraph Node implementations for Multi-Stage RAG-AQG generation, 2-layer validation, and persistence.

Session-level nodes (AQGState): retrieve_context -> generate_questions -> [fan-out] validate_question
-> review_results -> (top_up_questions -> [fan-out] validate_question ->) persist_questions.

Per-question nodes (QuestionState, run inside the validation subgraph for each candidate in parallel):
grounding_validation -> llm_judge_evaluation <-> self_refinement -> finalize_question.
"""

import asyncio
import functools
import hashlib
import inspect
import json
import logging
import math
import random
import re
import time
import uuid
from collections import defaultdict
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.database import get_session
from app.graph.state import AQGState, QuestionState
from app.models.db_models import ChatSession, Chunk, Question, ValidationLog
from app.services.chat.state_manager import ChatStateManager
from app.services.generation.schemas import (
    CognitivePlan,
    ContentAnalysis,
    QuestionBlueprint,
)
from app.services.generation.stage_runners import (
    run_llm_judge,
    run_refinement_a,
    run_refinement_b,
    run_stage1_context_understanding,
    run_stage2_cognitive_planning,
    run_stage3_question_blueprint,
    run_stage4_question_generation,
)
from app.services.retrieval.dense_index import DenseIndex
from app.services.retrieval.hybrid_search import HybridSearch, is_exercise_or_instruction_chunk
from app.services.retrieval.sparse_index import SparseIndex
from app.services.validation.grounding_checker import compute_grounding_evidence_score
from app.services.validation.quality_checks import (
    find_clarity_issue,
    has_valid_question_ending,
    validate_answer_quality,
)

logger = logging.getLogger(__name__)

# Chunk categories that carry book content (activity/discussion chunks produce "what did you do in class" questions)
_PREFERRED_CHUNK_CATEGORIES = {"materi_pokok", "uraian_materi", "studi_kasus"}
_MIN_CHUNK_CHARS = 200

# Used round-robin when the user does not ask for a specific level
MIXED_BLOOM_LEVELS = ["C1-Mengingat", "C2-Memahami", "C3-Mengaplikasikan", "C4-Menganalisis"]

# Supporting context appended after the focus chunk (generation, judge, and refinement all share it)
_SUPPORT_CONTEXT_CHARS = 2500

# Fast-fail reflective question regex patterns
REFLECTIVE_PATTERNS = [
    r"setelah mempelajari bab ini",
    r"tujuan pembelajaran",
    r"apa yang (?:sudah|telah) (?:kamu|kalian) pelajari",
    r"apa yang dapat kamu (?:lakukan|capai|raih)",
    r"apa yang perlu kamu lakukan untuk (?:mengetahui|memahami)",
    r"apa yang (?:kamu|kalian) (?:ketahui|pahami) tentang bab",
    r"apa manfaat mempelajari",
    r"mengapa kita perlu belajar",
    r"apa yang bisa kamu pelajari",
    r"apa yang ingin kamu ketahui",
]

# ── Global Service Singletons ──
_dense_index: DenseIndex | None = None
_sparse_cache: dict[str, SparseIndex] = {}
_chat_model_cache: dict[tuple[str, float], ChatOpenAI] = {}


def get_shared_dense_index() -> DenseIndex:
    """Get or create singleton DenseIndex."""
    global _dense_index
    if _dense_index is None:
        settings = get_settings()
        _dense_index = DenseIndex(
            persist_dir=settings.CHROMA_PERSIST_DIR,
            collection_name="rag_aqg_chunks",
            embedding_model_name=settings.EMBEDDING_MODEL,
        )
    return _dense_index


def get_chat_model(is_judge: bool = False, temperature: float | None = None) -> ChatOpenAI:
    """Get or create cached LangChain ChatModel with DeepInfra OpenAI-compatible API and structured JSON output."""
    settings = get_settings()
    model_name = settings.LLM_JUDGE_MODEL if is_judge else settings.LLM_GENERATOR_MODEL
    default_temp = 0.05 if is_judge else 0.3
    temp = temperature if temperature is not None else default_temp

    cache_key = (model_name, temp)
    if cache_key in _chat_model_cache:
        return _chat_model_cache[cache_key]

    api_key = settings.DEEPINFRA_API_KEY
    if not api_key:
        logger.warning(
            "DEEPINFRA_API_KEY is not configured in .env. LLM calls will require a valid DeepInfra token."
        )

    base_url = settings.DEEPINFRA_BASE_URL or "https://api.deepinfra.com/v1/openai"

    client = ChatOpenAI(
        model=model_name,
        api_key=api_key or "sk-dummy-key",
        base_url=base_url,
        temperature=temp,
        max_tokens=settings.MAX_TOKENS,
        timeout=settings.LLM_REQUEST_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
        model_kwargs={
            "response_format": {"type": "json_object"},
        },
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "RAG-AQG",
        },
    )
    _chat_model_cache[cache_key] = client
    return client


def _timed(node_name: str):
    """Log wall-clock duration of a graph node (sync or async)."""
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    logger.info("[Timing] node=%s %d ms", node_name, int((time.perf_counter() - t0) * 1000))
            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                logger.info("[Timing] node=%s %d ms", node_name, int((time.perf_counter() - t0) * 1000))
        return sync_wrapper
    return decorator


# ── Text Cleaning & Filtering Helpers ──

def extract_chapter_number(chapter_str: str | None) -> str | None:
    """Extract chapter number or roman numeral into normalized integer string."""
    if not chapter_str:
        return None
    match = re.search(
        r'\b(?:Bab|Chapter|Unit|Pembelajaran|Modul)?\s*([\d]+|[IVXLCDM]+)\b',
        str(chapter_str),
        re.IGNORECASE,
    )
    if match:
        val = match.group(1).upper()
        roman_map = {
            'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
            'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
        }
        return roman_map.get(val, val)
    return None


def sanitize_retrieval_query(user_prompt: str) -> str:
    """Clean user prompt from generation meta-words to extract pure topical keywords."""
    if not user_prompt:
        return ""
    text = user_prompt.lower()
    text = re.sub(r'\b\d+\s*(?:soal|pertanyaan)\b', '', text, flags=re.IGNORECASE)
    stop_meta = [
        r'\bbuatkan\b', r'\bbuat\b', r'\bbikin\b', r'\bgenerate\b', r'\bberikan\b', r'\bminta\b', r'\btolong\b',
        r'\bsoal\b', r'\bpertanyaan\b', r'\blatihan\b', r'\btugas\b', r'\bujicoba\b',
        r'\bc[1-6]\b', r'\besai\b', r'\bisian\s*singkat\b', r'\bisian\b', r'\bpilihan\s*ganda\b',
        r'\bdong\b', r'\bya\b', r'\bsebanyak\b', r'\bjumlah\b',
        # Chapter is handled separately; filler words carry no topic
        r'\bbab\s*[\w]+', r'\btentang\b', r'\bmengenai\b', r'\bmateri\b', r'\blevel\b', r'\btingkat\b',
        r'\bberagam\b', r'\bcampur\b', r'\bdari\b', r'\buntuk\b', r'\bdengan\b',
    ]
    for pattern in stop_meta:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^\w\s-]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def is_reflective_question(question_text: str) -> bool:
    """Check if question matches reflective / meta-learning patterns."""
    text_lower = question_text.lower().strip()
    return any(re.search(pattern, text_lower) for pattern in REFLECTIVE_PATTERNS)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r'\w+', text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def deduplicate_questions(
    questions: list[dict[str, Any]],
    threshold: float = 0.70,
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Deduplicate questions using Jaccard token overlap (also against already accepted `existing` ones)."""
    seen = [_tokens(e.get("question", "")) for e in (existing or [])]
    unique: list[dict[str, Any]] = []
    for cand in questions:
        c_tokens = _tokens(cand.get("question", ""))
        if not any(_jaccard(c_tokens, s) >= threshold for s in seen):
            unique.append(cand)
            seen.append(c_tokens)
    return unique


def deterministic_pre_pass_check(q: dict[str, Any], target_bloom: str) -> tuple[bool, str]:
    """Lightweight deterministic check before allowing auto-pass to skip LLM Judge."""
    q_text = q.get("question", "").strip()
    ans_text = q.get("answer", "").strip()

    if len(q_text) < 15:
        return False, "Pertanyaan terlalu pendek untuk evaluasi SD (< 15 karakter)."
    if len(ans_text) < 5:
        return False, "Jawaban terlalu singkat (< 5 karakter)."
    if not has_valid_question_ending(q_text):
        return False, "Pertanyaan tidak diakhiri tanda baca tanya atau seru."

    # C3-C4 should not be trivial 1-word recognition
    if any(b in target_bloom for b in ["C3", "C4"]) and len(ans_text.split()) < 3 and not any(
        w in q_text.lower()
        for w in ["mengapa", "bagaimana", "jelaskan", "analisis", "faktor", "sebab", "akibat", "apa yang terjadi"]
    ):
        return False, "Target C3/C4 membutuhkan pertanyaan analitis/aplikatif, bukan definisi satu kata."

    # General quality heuristics check
    quality_issues = validate_answer_quality(q)
    if quality_issues:
        return False, "; ".join(quality_issues)

    return True, "Validasi deterministik lolos."


def normalize_bloom_level(level: str | None) -> str | None:
    """Map a requested level to the SD range C1-C4; None means 'mixed levels'."""
    if not level:
        return None
    for full in MIXED_BLOOM_LEVELS:
        if full[:2] in level.upper():
            return full
    return "C2-Memahami"  # C5/C6 are out of scope for SD


def assign_bloom_levels(count: int, requested: str | None) -> list[str]:
    """Fixed level when requested, otherwise round-robin C1-C4 (10 -> 3/3/2/2)."""
    fixed = normalize_bloom_level(requested)
    if fixed:
        return [fixed] * count
    return [MIXED_BLOOM_LEVELS[i % len(MIXED_BLOOM_LEVELS)] for i in range(count)]


def select_diverse_chunks(
    chunks: list[dict[str, Any]],
    k: int,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Pick up to k content chunks spread over different sections (used when the request has no topic)."""
    rng = rng or random.Random()
    usable = [
        c for c in chunks
        if len(c.get("text", "")) >= _MIN_CHUNK_CHARS and not is_exercise_or_instruction_chunk(c.get("text", ""))
    ] or chunks
    preferred = [c for c in usable if c["metadata"].get("category") in _PREFERRED_CHUNK_CATEGORIES]
    pool = preferred if len(preferred) >= k else usable

    by_section: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in pool:
        meta = c["metadata"]
        by_section[(meta.get("chapter", ""), meta.get("section_heading", ""))].append(c)

    sections = list(by_section.values())
    rng.shuffle(sections)
    picked = [rng.choice(group) for group in sections[:k]]
    if len(picked) < k:
        picked_ids = {c["id"] for c in picked}
        rest = [c for c in pool if c["id"] not in picked_ids]
        picked += rng.sample(rest, min(k - len(picked), len(rest)))

    return sorted(picked, key=lambda c: c["metadata"].get("chunk_index", 0))


def find_best_chunk_for_focus(
    focus_point: str,
    testable_content: list[Any],
    retrieved_chunks: list[dict[str, Any]],
    fallback_index: int = 0,
) -> dict[str, Any]:
    """Match the most relevant chunk from retrieved chunks for a specific testable knowledge point."""
    if not retrieved_chunks:
        return {}

    # 1. Look for matching quote from testable_content
    for tc in testable_content:
        point = getattr(tc, "point", "") if not isinstance(tc, dict) else tc.get("point", "")
        quote = getattr(tc, "source_quote", "") if not isinstance(tc, dict) else tc.get("source_quote", "")
        if point == focus_point and quote:
            clean_q = quote.strip().lower()
            for chk in retrieved_chunks:
                if clean_q[:40] in chk.get("text", "").lower():
                    return chk

    # 2. Token overlap match between focus_point and chunk texts
    focus_tokens = set(re.findall(r'\w+', focus_point.lower()))
    if focus_tokens:
        best_chk = retrieved_chunks[fallback_index % len(retrieved_chunks)]
        best_score = -1
        for chk in retrieved_chunks:
            chk_tokens = set(re.findall(r'\w+', chk.get("text", "").lower()))
            overlap = len(focus_tokens & chk_tokens)
            if overlap > best_score:
                best_score = overlap
                best_chk = chk
        if best_score > 0:
            return best_chk

    # 3. Fallback to modulo index
    return retrieved_chunks[fallback_index % len(retrieved_chunks)]


def build_item_specs(
    retrieved: list[dict[str, Any]],
    analyses: dict[str, ContentAnalysis],
) -> list[dict[str, Any]]:
    """Interleave testable points across chunks (chunk A p1, chunk B p1, ..., chunk A p2, ...), dropping near-duplicates."""
    per_chunk: list[list[dict[str, Any]]] = []
    for chk in retrieved:
        ca = analyses.get(chk["id"])
        if ca is None:
            continue
        points = [tc.point for tc in ca.testable_content if tc.point] or ca.key_facts[:3] or [ca.topic or "Materi Pokok"]
        per_chunk.append([{"point": p, "chunk_id": chk["id"]} for p in points])

    specs: list[dict[str, Any]] = []
    seen: list[set[str]] = []
    for rank in range(max((len(p) for p in per_chunk), default=0)):
        for points in per_chunk:
            if rank < len(points):
                toks = _tokens(points[rank]["point"])
                if not any(_jaccard(toks, s) >= 0.6 for s in seen):
                    specs.append(points[rank])
                    seen.append(toks)
    return specs


def _merge_analyses(analyses: list[ContentAnalysis]) -> ContentAnalysis:
    """Combine per-chunk analyses into one overview for session-level cognitive planning (Stage 2)."""
    merged = ContentAnalysis(topic=next((a.topic for a in analyses if a.topic), "Materi Pembelajaran"))
    for a in analyses:
        merged.key_concepts += a.key_concepts[:2]
        merged.key_facts += a.key_facts[:2]
        merged.testable_content += a.testable_content[:2]
    return merged


def _source_reference(chunk: dict[str, Any]) -> str:
    meta = chunk.get("metadata", {})
    chap = meta.get("chapter", "")
    sec = meta.get("section_heading", "")
    page_num = meta.get("page_number")
    page_str = f" (Hal. {page_num})" if page_num else ""
    if chap and sec:
        return f"{chap} - {sec}{page_str}"
    if chap or sec:
        return f"{chap or sec}{page_str}"
    return f"Materi Buku{page_str}"


def _build_generation_context(primary: dict[str, Any], retrieved: list[dict[str, Any]]) -> str:
    """Focus chunk in full + supporting chunks. Stored on the candidate so the judge sees exactly this."""
    others = "\n\n".join(c.get("text", "") for c in retrieved if c.get("id") != primary.get("id"))
    if not others:
        return primary.get("text", "")
    return f"[FOKUS MATERI UTAMA]\n{primary.get('text', '')}\n\n[KONTEKS MATERI PENDUKUNG]\n{others[:_SUPPORT_CONTEXT_CHARS]}"


def _load_few_shot(document_id: str, bloom_level: str) -> str:
    """Two recent validated, clearly worded questions of the same level from this document."""
    with get_session() as db:
        past_qs = (
            db.query(Question)
            .join(ChatSession, Question.session_id == ChatSession.id)
            .filter(
                ChatSession.document_id == document_id,
                Question.status == "final",
                Question.bloom_level == bloom_level,
                Question.quality_warnings.is_(None),
            )
            .order_by(Question.created_at.desc())
            .limit(10)
            .all()
        )
        good = [
            q for q in past_qs
            if not find_clarity_issue(str(q.question_text)) and not is_reflective_question(str(q.question_text))
        ][:2]
        if not good:
            return "Tidak ada contoh tambahan."
        return "\n".join(
            f"Contoh {i}:\n  Pertanyaan: {q.question_text}\n  Jawaban: {q.answer_key}"
            for i, q in enumerate(good, 1)
        )


# ── Session-level Nodes (AQGState) ──

@_timed("retrieve_context")
def retrieve_context(state: AQGState) -> dict[str, Any]:
    """Node 1: Retrieve context chunks. Topic requests use hybrid search; topic-less requests sample diverse sections."""
    logger.info("[LangGraph Node 1] retrieve_context started for session_id='%s'", state["session_id"])
    settings = get_settings()

    document_id = state["document_id"]
    chapter = state.get("chapter")
    user_prompt = state.get("user_prompt", "")
    num_questions = state.get("num_questions", 5)
    top_k = min(settings.MAX_CONTEXT_CHUNKS, max(settings.RETRIEVAL_TOP_K, math.ceil(num_questions / 2)))

    with get_session() as db:
        chunks_db = db.query(Chunk).filter(Chunk.document_id == document_id).all()
        if not chunks_db:
            logger.error("No chunks found in DB for document_id='%s'", document_id)
            return {
                "retrieved_chunks": [],
                "source_chunk_ids": [],
                "error": f"Dokumen '{document_id}' belum diproses atau tidak memiliki chunk materi.",
            }

        chunks_data = [
            {
                "id": c.id,
                "text": c.text,
                "metadata": {
                    "document_id": c.document_id,
                    "category": c.category,
                    "chapter": c.chapter or "",
                    "section_heading": c.section_heading or "",
                    "page_number": getattr(c, "page_number", 1) or 1,
                    "chunk_index": getattr(c, "chunk_index", 0) or 0,
                    "section_type": getattr(c, "section_type", "materi_pokok") or "materi_pokok",
                },
            }
            for c in chunks_db
        ]

        manager = ChatStateManager(state["session_id"], db)
        chat_history = manager.get_context_summary()

    topic_query = sanitize_retrieval_query(user_prompt)
    expanded_chapter_title = ""

    if chapter:
        target_ch_num = extract_chapter_number(chapter)
        if target_ch_num:
            matched_chapter_chunks = [
                c for c in chunks_data
                if extract_chapter_number(c["metadata"].get("chapter", "")) == target_ch_num
            ]
            if matched_chapter_chunks:
                # Prioritize chunks strictly from this chapter
                chunks_data = matched_chapter_chunks
                expanded_chapter_title = matched_chapter_chunks[0]["metadata"].get("chapter", "")

    if not topic_query:
        # "Buatkan 10 soal" has no topic: searching with the raw prompt returns arbitrary chunks,
        # so spread the questions over different sections of the document/chapter instead.
        retrieved = select_diverse_chunks(chunks_data, top_k)
        logger.info("[LangGraph Node 1] No topic in prompt; sampled %d diverse chunks.", len(retrieved))
    else:
        query = topic_query
        if expanded_chapter_title:
            query = f"{query} {expanded_chapter_title}"

        # Build or reuse cached BM25 sparse index with robust content hash key
        content_hash = hashlib.md5("".join(c["id"] for c in chunks_data).encode()).hexdigest()[:12]
        cache_key = f"{document_id}_{len(chunks_data)}_{content_hash}"
        if cache_key not in _sparse_cache:
            sparse = SparseIndex()
            sparse.build_index(chunks_data)
            _sparse_cache[cache_key] = sparse
        else:
            sparse = _sparse_cache[cache_key]

        hybrid = HybridSearch(
            dense_index=get_shared_dense_index(),
            sparse_index=sparse,
            dense_weight=settings.HYBRID_DENSE_WEIGHT,
            sparse_weight=settings.HYBRID_SPARSE_WEIGHT,
        )
        candidates = hybrid.search(
            query=query,
            top_k=top_k * 2,
            document_id=document_id,
            candidate_k=settings.CANDIDATE_TOP_K,
            enable_rerank=settings.RERANKER_ENABLED,
        )
        if chapter and chunks_data:
            # Enforce strict chapter isolation: filter out any chunk from other chapters
            allowed_ids = {c["id"] for c in chunks_data}
            candidates = [c for c in candidates if c["id"] in allowed_ids]

        preferred = [
            c for c in candidates
            if (c.get("metadata") or {}).get("category") in _PREFERRED_CHUNK_CATEGORIES
        ]
        retrieved = (preferred if len(preferred) >= max(2, top_k // 2) else candidates)[:top_k]
        logger.info("[LangGraph Node 1] Selected %d context chunks with query='%s'.", len(retrieved), query)

    if not retrieved:
        retrieved = chunks_data[:top_k]

    return {
        "retrieved_chunks": retrieved,
        "source_chunk_ids": [c["id"] for c in retrieved],
        "chat_history": chat_history,
    }


async def _generate_candidates(
    state: AQGState,
    items: list[dict[str, Any]],
    stage_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run Stage 3 (blueprint) + Stage 4 (question package) for each item spec, in parallel."""
    retrieved = state.get("retrieved_chunks", [])
    chunk_by_id = {c["id"]: c for c in retrieved}
    generation_model = get_chat_model(is_judge=False, temperature=0.4)
    semaphore = asyncio.Semaphore(get_settings().GENERATION_CONCURRENCY)

    analyses = {cid: ContentAnalysis.model_validate(v["analysis"]) for cid, v in stage_cache["analyses"].items()}
    plans = {lvl: CognitivePlan.model_validate(v["plan"]) for lvl, v in stage_cache["plans"].items()}

    async def _generate_single_item(item: dict[str, Any]) -> dict[str, Any]:
        chk = chunk_by_id[item["chunk_id"]]
        level = item["bloom_level"]
        c_analysis = analyses[item["chunk_id"]]
        cog_plan = plans[level]
        src_ref = _source_reference(chk)
        gen_context = _build_generation_context(chk, retrieved)

        # Each question's trace holds only the stages that produced it
        step_traces = [stage_cache["analyses"][item["chunk_id"]]["trace"], stage_cache["plans"][level]["trace"]]

        async with semaphore:
            logger.info("[Multi-Stage Gen] Item (%s, Focus: '%s', Chunk: '%s')...", level, item["point"][:40], src_ref[:50])
            q_blueprint, t3 = await asyncio.to_thread(
                run_stage3_question_blueprint, generation_model, c_analysis, cog_plan, item["point"], 1,
            )
            step_traces.append(t3.model_dump())

            q_type = q_blueprint.question_type or cog_plan.recommended_question_format or "esai"
            q_pkg, t4 = await asyncio.to_thread(
                run_stage4_question_generation,
                generation_model,
                gen_context,
                q_blueprint,
                level,
                q_type,
                stage_cache["few_shots"].get(level, "Tidak ada contoh tambahan."),
                1,
            )
            step_traces.append(t4.model_dump())

        return {
            "question": q_pkg.question,
            "question_type": q_pkg.question_type or q_type,
            "answer": q_pkg.expected_answer,
            "explanation": q_pkg.explanation or f"Berdasarkan analisis materi '{c_analysis.topic}'. Poin uji: {q_blueprint.knowledge_point}.",
            "source_reference": src_ref,
            # The assigned level is authoritative; the model's echo of it is not
            "bloom_level": level,
            "knowledge_point": q_pkg.knowledge_point or q_blueprint.knowledge_point or item["point"],
            "grounding_evidence": q_pkg.grounding_evidence or q_blueprint.grounding_evidence,
            # Prompt Stage 4 tidak lagi meminta rubrik (sejak 49f1fa1), jadi biasanya kosong; tetap diteruskan bila model mengisinya
            "answer_elements": [e.model_dump() for e in q_pkg.answer_elements],
            "rubric": [r.model_dump() for r in q_pkg.rubric],
            "content_analysis": c_analysis.model_dump(),
            "cognitive_plan": cog_plan.model_dump(),
            "question_blueprint": q_blueprint.model_dump(),
            "context": gen_context,
            "stage_traces": step_traces,
            "chunk_id": chk["id"],
            "has_fallback": any(t.get("status") == "fallback" or t.get("has_fallback") for t in step_traces),
        }

    return list(await asyncio.gather(*[_generate_single_item(it) for it in items]))


@_timed("generate_questions")
async def generate_questions(state: AQGState) -> dict[str, Any]:
    """
    Node 2: Multi-Stage Question Generation.
    Stage 1 runs once per retrieved chunk and Stage 2 once per Bloom level (both in parallel);
    Stage 3 & 4 run concurrently per question item.
    """
    logger.info("[LangGraph Node 2] Multi-Stage generate_questions started")
    retrieved = state.get("retrieved_chunks", [])
    if not retrieved:
        return {"raw_questions": [], "error": state.get("error") or "Tidak ada konteks materi untuk pembuatan soal."}

    settings = get_settings()
    num_questions = state.get("num_questions", 5)
    candidate_count = num_questions + (1 if num_questions <= 3 else 2)
    levels = assign_bloom_levels(candidate_count, state.get("bloom_level"))
    distinct_levels = list(dict.fromkeys(levels))

    analysis_model = get_chat_model(is_judge=False, temperature=0.1)
    planning_model = get_chat_model(is_judge=False, temperature=0.2)
    semaphore = asyncio.Semaphore(settings.GENERATION_CONCURRENCY)

    async def _limited(fn, *args):
        async with semaphore:
            return await asyncio.to_thread(fn, *args)

    # ── Stage 1: Context Understanding, one call per chunk so every testable point keeps its source chunk ──
    stage1 = await asyncio.gather(*[
        _limited(run_stage1_context_understanding, analysis_model, chk.get("text", ""), 1) for chk in retrieved
    ])
    analyses = {chk["id"]: ca for chk, (ca, _) in zip(retrieved, stage1, strict=True)}

    # ── Stage 2: Cognitive Bloom Planning, one call per target level ──
    merged = _merge_analyses(list(analyses.values()))
    stage2 = await asyncio.gather(*[
        _limited(run_stage2_cognitive_planning, planning_model, merged, lvl, 1) for lvl in distinct_levels
    ])

    stage_cache = {
        "analyses": {
            chk["id"]: {"analysis": ca.model_dump(), "trace": t.model_dump()}
            for chk, (ca, t) in zip(retrieved, stage1, strict=True)
        },
        "plans": {
            lvl: {"plan": plan.model_dump(), "trace": t.model_dump()}
            for lvl, (plan, t) in zip(distinct_levels, stage2, strict=True)
        },
        "few_shots": {
            lvl: _load_few_shot(state["document_id"], lvl) for lvl in MIXED_BLOOM_LEVELS
        },
    }

    specs = build_item_specs(retrieved, analyses)
    logger.info("[Node 2] %d distinct knowledge points from %d chunks.", len(specs), len(retrieved))
    items = [{**specs[i % len(specs)], "bloom_level": levels[i]} for i in range(candidate_count)]
    spare_items = specs[candidate_count:]

    candidates = await _generate_candidates(state, items, stage_cache)
    deduped = deduplicate_questions(candidates, threshold=0.70)
    logger.info("[Node 2] Generated %d candidates (%d after dedup).", len(candidates), len(deduped))

    return {
        "raw_questions": deduped,
        "spare_items": spare_items,
        "stage_cache": stage_cache,
    }


def fan_out_validation(state: AQGState):
    """Send every candidate of the current round to its own isolated validation run."""
    from langgraph.graph import END
    from langgraph.types import Send

    raw_qs = state.get("raw_questions", [])
    if not raw_qs:
        if state.get("validated_questions"):
            return "persist_questions"
        logger.warning("[Edge] No candidate questions generated -> END")
        return END

    max_attempts = get_settings().MAX_REFINEMENT_ATTEMPTS
    logger.info("[Edge] Fan-out %d candidates -> validate_question", len(raw_qs))
    return [
        Send("validate_question", {
            "question": {k: v for k, v in q.items() if k not in ("stage_traces", "context")},
            "context": q.get("context", ""),
            "session_bloom_level": state.get("bloom_level"),
            "attempt": 1,
            "max_attempts": max_attempts,
            "failed_stage": "none",
            "judge_evaluation": None,
            "validation_logs": [],
            "stage_traces": list(q.get("stage_traces", [])),
        })
        for q in raw_qs
    ]


async def validate_question(state: QuestionState) -> dict[str, Any]:
    """Run the per-question validation subgraph and hand the result back to the session state."""
    from app.graph.workflow import get_validation_graph

    result = await get_validation_graph().ainvoke(state)
    q = dict(result["question"])
    q["validation_logs"] = result.get("validation_logs", [])
    q["stage_traces"] = result.get("stage_traces", [])
    return {"validated_questions": [q]}


def review_results(state: AQGState) -> dict[str, Any]:
    """Fan-in point: summarize the validation round."""
    validated = state.get("validated_questions", [])
    n_final = sum(1 for q in validated if q.get("status") == "final")
    logger.info("[Node Review] %d/%d candidates passed (target %d).", n_final, len(validated), state.get("num_questions", 5))
    return {}


@_timed("top_up_questions")
async def top_up_questions(state: AQGState) -> dict[str, Any]:
    """Generate replacement candidates for questions that did not pass validation (one round only)."""
    validated = state.get("validated_questions", [])
    n_final = sum(1 for q in validated if q.get("status") == "final")
    deficit = max(0, state.get("num_questions", 5) - n_final)
    count = deficit + 1

    # Keep the requested level mix: replace failed questions with the same levels
    failed_levels = [q["bloom_level"] for q in validated if q.get("status") != "final"]
    levels = (failed_levels + assign_bloom_levels(count, state.get("bloom_level")))[:count]

    spare = list(state.get("spare_items", []))
    used_points = {q.get("knowledge_point", "") for q in validated}
    if len(spare) < count:
        # Fall back to points already used, preferring those whose question failed
        reuse = [
            {"point": q.get("knowledge_point", ""), "chunk_id": q["chunk_id"]}
            for q in validated if q.get("status") != "final" and q.get("chunk_id")
        ]
        spare += reuse
    if not spare:
        return {"raw_questions": [], "top_up_done": True}

    items = [{**spare[i % len(spare)], "bloom_level": levels[i]} for i in range(count)]
    logger.info("[Node TopUp] Generating %d replacement candidates (deficit %d, %d unused points).",
                count, deficit, len([s for s in spare if s["point"] not in used_points]))

    candidates = await _generate_candidates(state, items, state["stage_cache"])
    deduped = deduplicate_questions(candidates, threshold=0.70, existing=validated)
    return {
        "raw_questions": deduped,
        "spare_items": spare[count:],
        "top_up_done": True,
    }


def _prune_stage_traces_for_db(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cap very long prompts to keep SQLite small. Raw responses are kept whole so their JSON stays readable."""
    pruned_list = []
    for tr in traces:
        t_copy = tr.copy() if isinstance(tr, dict) else tr
        prompt = t_copy.get("prompt_sent") if isinstance(t_copy, dict) else None
        if isinstance(prompt, str) and len(prompt) > 6000:
            t_copy["prompt_sent"] = prompt[:6000] + "... [truncated for storage]"
        pruned_list.append(t_copy)
    return pruned_list


def _bloom_order(q: dict[str, Any]) -> int:
    level = q.get("bloom_level", "")
    return next((i for i, lvl in enumerate(MIXED_BLOOM_LEVELS) if lvl[:2] in level), len(MIXED_BLOOM_LEVELS))


@_timed("persist_questions")
def persist_questions(state: AQGState) -> dict[str, Any]:
    """Node 6: Choose the best `num_questions` (passed first, then needs_review) and save them with their own logs/traces."""
    logger.info("[LangGraph Node 6] persist_questions started")
    session_id = state["session_id"]
    source_chunk_ids = state.get("source_chunk_ids", [])
    num_questions = state.get("num_questions", 5)
    validated = state.get("validated_questions", [])

    finals = [q for q in validated if q.get("status") == "final"]
    reviews = [q for q in validated if q.get("status") != "final"]
    selected = sorted((finals + reviews)[:num_questions], key=_bloom_order)

    saved: list[dict[str, Any]] = []
    with get_session() as db:
        for q in selected:
            q = dict(q)
            q_id = str(uuid.uuid4())
            q["id"] = q_id
            q["source_reference"] = q.get("source_reference") or "Materi Buku"
            q["explanation"] = q.get("explanation") or f"Penjelasan berdasarkan materi {q.get('knowledge_point', '')}."

            quality_issues = validate_answer_quality(q)
            primary_cid = q.get("chunk_id")
            ordered_chunk_ids = (
                [primary_cid] + [cid for cid in source_chunk_ids if cid != primary_cid]
                if primary_cid else source_chunk_ids
            )

            db.add(Question(
                id=q_id,
                session_id=session_id,
                chunk_ids=json.dumps(ordered_chunk_ids, ensure_ascii=False),
                question_type=q.get("question_type", "esai"),
                question_text=q.get("question", ""),
                options=json.dumps(q.get("options", {}), ensure_ascii=False) if q.get("options") else None,
                answer_key=q.get("answer", ""),
                explanation=q["explanation"],
                source_reference=q["source_reference"],
                bloom_level=q.get("bloom_level") or "C2-Memahami",
                status=q.get("status", "needs_review"),
                refinement_count=q.get("refinement_count", 0),
                rubric=json.dumps(q.get("rubric", []), ensure_ascii=False),
                answer_elements=json.dumps(q.get("answer_elements", []), ensure_ascii=False),
                grounding_evidence=q.get("grounding_evidence", ""),
                knowledge_point=q.get("knowledge_point", ""),
                prompt_traces=json.dumps(_prune_stage_traces_for_db(q.get("stage_traces", [])), ensure_ascii=False),
                quality_warnings=json.dumps(quality_issues, ensure_ascii=False) if quality_issues else None,
            ))

            # Only this question's own validation attempts
            for log_item in q.get("validation_logs", []):
                db.add(ValidationLog(
                    question_id=q_id,
                    attempt_number=log_item.get("attempt_number", 1),
                    layer=log_item.get("layer", "grounding"),
                    score_or_verdict=log_item.get("score_or_verdict", ""),
                    feedback=log_item.get("feedback", ""),
                    aspect_evaluations=log_item.get("aspect_evaluations"),
                ))
            saved.append(q)

        db.commit()

    logger.info(
        "[Node 6] Persisted %d questions (%d final, %d needs_review) out of %d validated candidates.",
        len(saved), sum(q["status"] == "final" for q in saved), sum(q["status"] != "final" for q in saved), len(validated),
    )
    return {"finalized_questions": saved}


# ── Per-question Validation Nodes (QuestionState) ──

def _log(attempt: int, layer: str, verdict: str, score_or_verdict: str, feedback: str, aspects: str | None = None) -> dict[str, Any]:
    return {
        "attempt_number": attempt,
        "layer": layer,
        "score_or_verdict": score_or_verdict,
        "feedback": feedback,
        "aspect_evaluations": aspects,
        "auto_pass": False,
        "verdict": verdict,
    }


def grounding_validation(state: QuestionState) -> dict[str, Any]:
    """
    Layer 1: deterministic pre-check, then Fast-Reject grounding similarity between QA and grounding evidence.
    Score < threshold triggers refinement; otherwise proceed to the LLM Judge (Layer 2).
    """
    settings = get_settings()
    q = state["question"]
    attempt = state["attempt"]
    logs = list(state.get("validation_logs", []))

    q_text = q.get("question", "")
    if not q_text:
        logs.append(_log(attempt, "grounding", "fail", "fail (empty_question)", "Soal kosong."))
        return {"validation_logs": logs, "failed_stage": "generation"}

    logger.info("[Validation] grounding (attempt %d) for: '%s'", attempt, q_text[:60])

    # Pre-check: reflective, classroom-referencing, or multi-question items are rejected before spending a judge call
    if is_reflective_question(q_text):
        logs.append(_log(attempt, "pre_check", "fail", "fail (reflective_pattern)",
                         "Soal bersifat reflektif / meta-learning. Ganti dengan fakta/teori/konsep konkret dari buku."))
        return {"validation_logs": logs, "failed_stage": "generation"}
    clarity_issue = find_clarity_issue(q_text)
    if clarity_issue:
        logs.append(_log(attempt, "pre_check", "fail", "fail (unclear_question)", clarity_issue))
        return {"validation_logs": logs, "failed_stage": "generation"}

    grounding_res = compute_grounding_evidence_score(
        question_text=q_text,
        answer_text=q.get("answer", ""),
        grounding_evidence=q.get("grounding_evidence", ""),
        fallback_chunks=[state.get("context", "")] if state.get("context") else [],
        dense_idx=get_shared_dense_index(),
    )
    g_score = grounding_res["score"]
    fast_reject_thr = settings.FAST_REJECT_THRESHOLD
    aspects = json.dumps({"grounding_similarity": g_score, "target": grounding_res["target"]}, ensure_ascii=False)

    if g_score < fast_reject_thr:
        logs.append(_log(
            attempt, "grounding", "fail", f"fail (fast_reject score={g_score:.3f})",
            f"Grounding similarity sangat rendah ({g_score:.3f} < {fast_reject_thr:.2f}). Jawaban tidak selaras dengan materi teks buku.",
            aspects,
        ))
        return {"validation_logs": logs, "failed_stage": "generation"}

    logs.append(_log(
        attempt, "grounding", "pass", f"pass (score={g_score:.3f})",
        f"Lolos Fast-Reject (similarity={g_score:.3f}). Diteruskan ke LLM-as-Judge.",
        aspects,
    ))
    return {"validation_logs": logs, "failed_stage": "none"}


async def llm_judge_evaluation(state: QuestionState) -> dict[str, Any]:
    """
    Layer 2: Evaluate question using LLM-as-Judge across 5 dimensions:
    grounding, bloom_adherence, bahasa, answerability, answer_alignment.
    """
    q = dict(state["question"])
    attempt = state["attempt"]
    target_bloom = q.get("bloom_level") or state.get("session_bloom_level") or "C2-Memahami"

    judge_eval, judge_trace = await asyncio.to_thread(
        run_llm_judge,
        judge_model=get_chat_model(is_judge=True, temperature=0.05),
        retrieved_context=state.get("context", ""),
        grounding_evidence=q.get("grounding_evidence", ""),
        question=q.get("question", ""),
        expected_answer=q.get("answer", ""),
        explanation=q.get("explanation", ""),
        target_bloom_level=target_bloom,
        attempt=attempt,
    )

    verdict = judge_eval.overall.lower().strip()
    failed_stage = judge_eval.failed_stage.lower().strip() if verdict != "pass" else "none"
    if verdict != "pass" and failed_stage not in ("generation", "planning"):
        failed_stage = "generation"
    logger.info("[Validation] judge overall='%s', failed_stage='%s' (attempt %d)", verdict, failed_stage, attempt)

    feedback_parts = []
    for aspect_name in ["grounding", "bloom_adherence", "bahasa", "answerability", "answer_alignment"]:
        asp: Any = getattr(judge_eval, aspect_name, None)
        if asp and getattr(asp, "status", "") == "fail":
            feedback_parts.append(f"[{aspect_name.upper()}] {asp.feedback}")
    full_feedback = " ; ".join(feedback_parts) if feedback_parts else "Semua aspek evaluasi juri lolos."

    logs = list(state.get("validation_logs", []))
    logs.append(_log(
        attempt, "judge", verdict, f"{verdict} (failed_stage={failed_stage})", full_feedback,
        json.dumps(judge_eval.model_dump(), ensure_ascii=False),
    ))

    return {
        "validation_logs": logs,
        "failed_stage": failed_stage,
        "judge_evaluation": judge_eval.model_dump(),
        "stage_traces": [*state.get("stage_traces", []), judge_trace.model_dump()],
    }


async def self_refinement(state: QuestionState) -> dict[str, Any]:
    """
    Smart Self-Refinement Router:
    - failed_stage == "planning" -> Refinement Prompt B (re-plans Bloom & Blueprint) -> re-generates.
    - otherwise -> Refinement Prompt A (repairs wording/grounding/explanation).
    """
    attempt = state["attempt"] + 1
    q = dict(state["question"])
    logs = state.get("validation_logs", [])
    last_feedback = logs[-1].get("feedback", "Perbaiki soal agar lebih konkret.") if logs else "Perbaiki soal."
    failed_stage = state.get("failed_stage") or "generation"
    context_str = state.get("context", "")

    logger.info("[Validation] self_refinement attempt %d/%d (failed_stage='%s')", attempt, state["max_attempts"], failed_stage)

    chat_model = get_chat_model(is_judge=False, temperature=0.2)
    curr_traces = list(state.get("stage_traces", []))
    target_bloom = q.get("bloom_level") or state.get("session_bloom_level") or "C2-Memahami"

    c_analysis = ContentAnalysis.model_validate(q.get("content_analysis") or {})
    cog_plan = CognitivePlan.model_validate(q.get("cognitive_plan") or {})
    q_blueprint = QuestionBlueprint.model_validate(q.get("question_blueprint") or {})

    if failed_stage == "planning":
        judge_eval_data = state.get("judge_evaluation") or {}
        detected_level = (judge_eval_data.get("bloom_adherence") or {}).get("detected_level") or "Mismatch"

        new_plan, t_ref_b = await asyncio.to_thread(
            run_refinement_b,
            chat_model=chat_model,
            prev_plan=cog_plan,
            question_text=q.get("question", ""),
            validation_feedback=last_feedback,
            detected_level=detected_level,
            target_bloom_level=target_bloom,
            content_analysis=c_analysis,
            attempt=attempt,
        )
        curr_traces.append(t_ref_b.model_dump())

        # Re-run Stage 3 Blueprint with new cognitive plan, keeping the same knowledge point
        new_blueprint, t_bp = await asyncio.to_thread(
            run_stage3_question_blueprint, chat_model, c_analysis, new_plan, q.get("knowledge_point"), attempt,
        )
        curr_traces.append(t_bp.model_dump())

        new_pkg, t_gen = await asyncio.to_thread(
            run_stage4_question_generation,
            chat_model=chat_model,
            retrieved_context=context_str,
            blueprint=new_blueprint,
            target_bloom_level=target_bloom,
            question_type=new_blueprint.question_type or "esai",
            few_shot_examples="Tidak ada contoh tambahan.",
            attempt=attempt,
        )
        curr_traces.append(t_gen.model_dump())

        q["question_type"] = new_pkg.question_type or new_blueprint.question_type or q.get("question_type", "esai")
        q["grounding_evidence"] = new_pkg.grounding_evidence or new_blueprint.grounding_evidence
        q["cognitive_plan"] = new_plan.model_dump()
        q["question_blueprint"] = new_blueprint.model_dump()
        q["has_fallback"] = q.get("has_fallback") or t_gen.has_fallback
    else:
        new_pkg, t_ref_a = await asyncio.to_thread(
            run_refinement_a,
            chat_model=chat_model,
            question=q.get("question", ""),
            expected_answer=q.get("answer", ""),
            explanation=q.get("explanation", ""),
            blueprint=q_blueprint,
            retrieved_context=context_str,
            validation_feedback=last_feedback,
            target_bloom_level=target_bloom,
            question_type=q.get("question_type", "esai"),
            attempt=attempt,
        )
        curr_traces.append(t_ref_a.model_dump())
        q["grounding_evidence"] = new_pkg.grounding_evidence or q_blueprint.grounding_evidence

    q["question"] = new_pkg.question
    q["answer"] = new_pkg.expected_answer
    q["explanation"] = new_pkg.explanation or q.get("explanation", "")
    q["answer_elements"] = [e.model_dump() for e in new_pkg.answer_elements]
    q["rubric"] = [r.model_dump() for r in new_pkg.rubric]

    return {"question": q, "attempt": attempt, "stage_traces": curr_traces}


def finalize_question(state: QuestionState) -> dict[str, Any]:
    """Set the final status: 'final' only if the last judge verdict passed without fallback stages."""
    q = dict(state["question"])
    logs = state.get("validation_logs", [])
    last = logs[-1] if logs else {}
    passed = last.get("layer") == "judge" and last.get("verdict") == "pass"

    q["status"] = "final" if passed and not q.get("has_fallback") else "needs_review"
    q["refinement_count"] = state["attempt"] - 1
    logger.info("[Validation] finalize '%s' -> %s after %d attempt(s)", q.get("question", "")[:50], q["status"], state["attempt"])
    return {"question": q}
