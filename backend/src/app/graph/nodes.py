"""LangGraph Node implementations for Multi-Stage RAG-AQG generation, 2-layer validation, and persistence."""

import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import Any

import numpy as np
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.database import get_session
from app.graph.state import AQGState
from app.models.db_models import Chunk, Question, ValidationLog
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
from app.services.retrieval.hybrid_search import HybridSearch
from app.services.retrieval.sparse_index import SparseIndex
from app.services.validation.grounding_checker import compute_grounding_evidence_score
from app.services.validation.quality_checks import validate_answer_quality

logger = logging.getLogger(__name__)

# Allowed chunk categories for question generation context
_ALLOWED_CHUNK_CATEGORIES = {"KONSEP", "NARASI"}

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
        max_retries=5,
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
    ]
    for pattern in stop_meta:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def is_reflective_question(question_text: str) -> bool:
    """Check if question matches reflective / meta-learning patterns."""
    text_lower = question_text.lower().strip()
    return any(re.search(pattern, text_lower) for pattern in REFLECTIVE_PATTERNS)


def deduplicate_questions(questions: list[dict[str, Any]], threshold: float = 0.70) -> list[dict[str, Any]]:
    """Deduplicate questions using Jaccard token overlap."""
    def tokenize(t: str) -> set:
        return set(re.findall(r'\w+', t.lower()))

    def jaccard(a: set, b: set) -> float:
        union = a | b
        return len(a & b) / len(union) if union else 0.0

    unique: list[dict[str, Any]] = []
    for cand in questions:
        c_tokens = tokenize(cand.get("question", ""))
        if not any(jaccard(c_tokens, tokenize(e.get("question", ""))) >= threshold for e in unique):
            unique.append(cand)

    return unique


def deterministic_pre_pass_check(q: dict[str, Any], target_bloom: str) -> tuple[bool, str]:
    """Lightweight deterministic check before allowing auto-pass to skip LLM Judge."""
    q_text = q.get("question", "").strip()
    ans_text = q.get("answer", "").strip()

    if len(q_text) < 15:
        return False, "Pertanyaan terlalu pendek untuk evaluasi SD (< 15 karakter)."
    if len(ans_text) < 5:
        return False, "Jawaban terlalu singkat (< 5 karakter)."
    if not q_text.endswith(("?", "!")):
        return False, "Pertanyaan tidak diakhiri tanda baca tanya atau seru."

    # C3-C4 should not be trivial 1-word recognition
    if any(b in target_bloom for b in ["C3", "C4"]):
        if len(ans_text.split()) < 3 and not any(
            w in q_text.lower()
            for w in ["mengapa", "bagaimana", "jelaskan", "analisis", "faktor", "sebab", "akibat", "apa yang terjadi"]
        ):
            return False, "Target C3/C4 membutuhkan pertanyaan analitis/aplikatif, bukan definisi satu kata."

    # General quality heuristics check
    quality_issues = validate_answer_quality(q)
    if quality_issues:
        return False, "; ".join(quality_issues)

    return True, "Validasi deterministik lolos."


def enforce_topic_diversity(
    questions: list[dict[str, Any]],
    dense_idx: DenseIndex,
    min_diversity: float = 0.25,
) -> list[dict[str, Any]]:
    """Ensure questions cover diverse knowledge points via embedding distance."""
    if len(questions) <= 1:
        return questions

    kp_texts = [q.get("knowledge_point") or q.get("question", "") for q in questions]
    embeddings = dense_idx.model.encode(kp_texts, normalize_embeddings=True)

    selected = [questions[0]]
    selected_embs = [embeddings[0]]
    remaining = []

    for i in range(1, len(questions)):
        max_sim = max(float(np.dot(embeddings[i], se)) for se in selected_embs)
        if max_sim < (1.0 - min_diversity):
            selected.append(questions[i])
            selected_embs.append(embeddings[i])
        else:
            remaining.append((max_sim, questions[i]))

    # If diversity filter removed too many, fill with the least similar remaining candidates
    if len(selected) < len(questions) and remaining:
        remaining.sort(key=lambda x: x[0])  # lowest similarity first
        for _, q in remaining:
            selected.append(q)
            if len(selected) >= len(questions):
                break

    return selected

    return selected


# ── LangGraph Nodes ──

def retrieve_context(state: AQGState) -> dict[str, Any]:
    """Node 1: Retrieve relevant context chunks using Document-Filtered Hybrid Search, Query Expansion, and Reranking."""
    logger.info("[LangGraph Node 1] retrieve_context started for session_id='%s'", state["session_id"])
    settings = get_settings()
    dense_idx = get_shared_dense_index()

    document_id = state["document_id"]
    chapter = state.get("chapter")
    user_prompt = state.get("user_prompt", "")

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

    # Query Transformation & Chapter Topic Expansion
    clean_query = sanitize_retrieval_query(user_prompt) or user_prompt
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
                # Extract full chapter title (e.g. "Bab 2: Sistem Pencernaan Manusia")
                first_chap_name = matched_chapter_chunks[0]["metadata"].get("chapter", "")
                if first_chap_name:
                    expanded_chapter_title = first_chap_name

    if expanded_chapter_title:
        clean_query = f"{clean_query} {expanded_chapter_title}".strip()
    elif chapter:
        clean_query = f"{clean_query} Bab {chapter}".strip()

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
        dense_index=dense_idx,
        sparse_index=sparse,
        dense_weight=settings.HYBRID_DENSE_WEIGHT,
        sparse_weight=settings.HYBRID_SPARSE_WEIGHT,
    )

    retrieved = hybrid.search(
        query=clean_query,
        top_k=settings.RETRIEVAL_TOP_K,
        document_id=document_id,
        candidate_k=settings.CANDIDATE_TOP_K,
        enable_rerank=settings.RERANKER_ENABLED,
    )
    if chapter and chunks_data:
        # Enforce strict chapter isolation: filter out any chunk from other chapters
        allowed_ids = {c["id"] for c in chunks_data}
        retrieved = [c for c in retrieved if c["id"] in allowed_ids]

    if not retrieved:
        retrieved = chunks_data[:settings.RETRIEVAL_TOP_K]

    source_chunk_ids = [c["id"] for c in retrieved]
    logger.info("[LangGraph Node 1] Selected %d context chunks with query='%s'.", len(retrieved), clean_query)

    return {
        "retrieved_chunks": retrieved,
        "source_chunk_ids": source_chunk_ids,
        "chat_history": chat_history,
    }


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


async def generate_questions(state: AQGState) -> dict[str, Any]:
    """
    Node 2: Multi-Stage Question Generation.
    Stage 1 & 2 run 1x for the material/session.
    Stage 3 & 4 run concurrently per question item.
    """
    logger.info("[LangGraph Node 2] Multi-Stage generate_questions started")
    retrieved = state.get("retrieved_chunks", [])
    if not retrieved:
        return {"raw_questions": [], "current_question": {}, "error": "Tidak ada konteks materi untuk pembuatan soal."}

    num_questions = state.get("num_questions", 5)
    bloom_level_raw = state.get("bloom_level") or "C2-Memahami"
    # Ensure SD Bloom range C1-C4
    bloom_level = bloom_level_raw if any(b in bloom_level_raw for b in ["C1", "C2", "C3", "C4"]) else "C2-Memahami"

    # Adaptive temperature models per stage
    analysis_model = get_chat_model(is_judge=False, temperature=0.1)
    planning_model = get_chat_model(is_judge=False, temperature=0.2)
    generation_model = get_chat_model(is_judge=False, temperature=0.4)

    # ── Level Sesi/Materi: Gabungkan konteks untuk analisis komprehensif ──
    combined_context = "\n\n---\n\n".join(chk.get("text", "") for chk in retrieved[:5])

    # ── Stage 1: Context Understanding (DIJALANKAN 1 KALI untuk topik materi) ──
    logger.info("[Multi-Stage Gen] Running Stage 1: Context Understanding (1x across retrieved context)...")
    c_analysis, t1 = await asyncio.to_thread(
        run_stage1_context_understanding, analysis_model, combined_context, 1
    )

    # ── Stage 2: Cognitive Bloom Planning (DIJALANKAN 1 KALI untuk target Bloom level) ──
    logger.info("[Multi-Stage Gen] Running Stage 2: Cognitive Bloom Planning (1x for target level %s)...", bloom_level)
    cog_plan, t2 = await asyncio.to_thread(
        run_stage2_cognitive_planning, planning_model, c_analysis, bloom_level, 1
    )

    # ── Retrieve Few-Shot Examples from past validated questions ──
    few_shot_str = "Tidak ada contoh tambahan."
    with get_session() as db:
        past_qs = (
            db.query(Question)
            .filter(
                Question.session_id == state["session_id"],
                Question.status == "final",
                Question.bloom_level == bloom_level,
            )
            .order_by(Question.created_at.desc())
            .limit(2)
            .all()
        )
        if not past_qs:
            # Fallback to any past validated question with the same bloom level across the document
            past_qs = (
                db.query(Question)
                .filter(
                    Question.status == "final",
                    Question.bloom_level == bloom_level,
                )
                .order_by(Question.created_at.desc())
                .limit(2)
                .all()
            )
        if past_qs:
            examples = []
            for i, q in enumerate(past_qs, 1):
                examples.append(
                    f"Contoh {i}:\n  Pertanyaan: {q.question_text}\n  Jawaban: {q.answer_key}"
                )
            few_shot_str = "\n".join(examples)

    # ── Level Butir Soal: Concurrent Execution Stage 3 (Blueprint) & Stage 4 (Package) ──
    testable_points = [tc.point for tc in c_analysis.testable_content if tc.point]
    if not testable_points and c_analysis.key_facts:
        testable_points = c_analysis.key_facts
    if not testable_points:
        testable_points = [c_analysis.topic or "Materi Pokok"]

    target_count = num_questions + (1 if num_questions <= 3 else 2)
    semaphore = asyncio.Semaphore(3)  # Rate limit safe: max 3 concurrent items

    async def _generate_single_item(q_idx: int) -> dict[str, Any]:
        async with semaphore:
            focus_point = testable_points[q_idx % len(testable_points)]
            chk = find_best_chunk_for_focus(
                focus_point,
                c_analysis.testable_content,
                retrieved,
                fallback_index=q_idx,
            )
            chunk_text = chk.get("text", "")
            chunk_meta = chk.get("metadata", {})
            chap = chunk_meta.get("chapter", "")
            sec = chunk_meta.get("section_heading", "")
            page_num = chunk_meta.get("page_number")
            page_str = f" (Hal. {page_num})" if page_num else ""

            if chap and sec:
                src_ref = f"{chap} - {sec}{page_str}"
            elif chap:
                src_ref = f"{chap}{page_str}"
            elif sec:
                src_ref = f"{sec}{page_str}"
            else:
                src_ref = f"Materi Buku{page_str}"

            logger.info("[Multi-Stage Gen] Item %d/%d (Focus: '%s', Chunk: '%s')...",
                        q_idx + 1, target_count, focus_point[:40], src_ref[:50])

            step_traces = [t1.model_dump(), t2.model_dump()]

            # Stage 3: Question Blueprint
            q_blueprint, t3 = await asyncio.to_thread(
                run_stage3_question_blueprint,
                generation_model,
                c_analysis,
                cog_plan,
                focus_point,
                1,
            )
            step_traces.append(t3.model_dump())

            # Stage 4: Question Generation with Parent Context Window Expansion
            primary_text = chunk_text
            other_texts = [c.get("text", "") for c in retrieved if c.get("id") != chk.get("id")]
            combined_surrounding = "\n\n".join(other_texts)
            if combined_surrounding:
                gen_context = f"[FOKUS MATERI UTAMA]\n{primary_text}\n\n[KONTEKS MATERI PENDUKUNG]\n{combined_surrounding[:2500]}"
            else:
                gen_context = primary_text

            q_pkg, t4 = await asyncio.to_thread(
                run_stage4_question_generation,
                generation_model,
                gen_context,
                q_blueprint,
                bloom_level,
                q_blueprint.question_type or "esai",
                few_shot_str,
                1,
            )
            step_traces.append(t4.model_dump())

            # Fallback tagging check
            has_fallback_stage = any(
                t.get("status") == "fallback" or t.get("has_fallback")
                for t in step_traces
            )

            candidate_obj = {
                "question": q_pkg.question,
                "question_type": q_pkg.question_type,
                "answer": q_pkg.expected_answer,
                "explanation": q_pkg.explanation or f"Berdasarkan analisis materi '{c_analysis.topic}'. Poin uji: {q_blueprint.knowledge_point}.",
                "source_reference": src_ref,
                "bloom_level": q_pkg.cognitive_level or bloom_level,
                "knowledge_point": q_pkg.knowledge_point or q_blueprint.knowledge_point,
                "grounding_evidence": q_pkg.grounding_evidence or q_blueprint.grounding_evidence,
                "answer_elements": [],
                "rubric": [],
                "question_blueprint": q_blueprint.model_dump(),
                "stage_traces": step_traces,
                "chunk_id": chk.get("id"),
                "status": "needs_review" if has_fallback_stage else "final",
            }
            return candidate_obj

    tasks = [_generate_single_item(i) for i in range(target_count)]
    candidates = list(await asyncio.gather(*tasks))

    # Deduplicate candidate questions
    dense_idx = get_shared_dense_index()
    deduped = deduplicate_questions(candidates, threshold=0.70)
    deduped = enforce_topic_diversity(deduped, dense_idx, min_diversity=0.30)
    final_raw = deduped[:num_questions]
    logger.info("[Node 2] Generated %d deduplicated multi-stage question packages.", len(final_raw))

    first_q = final_raw[0] if final_raw else {}
    first_traces = first_q.get("stage_traces", [])

    return {
        "raw_questions": final_raw,
        "current_q_index": 0,
        "current_question": first_q,
        "content_analysis": c_analysis.model_dump(),
        "cognitive_plan": cog_plan.model_dump(),
        "question_blueprint": first_q.get("question_blueprint", {}),
        "stage_traces": first_traces,
        "current_attempt": 1,
        "max_attempts": get_settings().MAX_REFINEMENT_ATTEMPTS,
        "failed_stage": "none",
        "validation_logs": [],
    }


def grounding_validation(state: AQGState) -> dict[str, Any]:
    """
    Node 3 (Layer 1): Fast-Reject Grounding Validation.
    Calculates cosine similarity embeddings between QA and blueprint grounding evidence.
    Score < 0.40 triggers Fast-Reject (Refinement). Score >= 0.40 proceeds to LLM Judge (Layer 2).
    """
    settings = get_settings()
    dense_idx = get_shared_dense_index()
    q = state.get("current_question", {})
    if not q or not q.get("question"):
        logger.warning("[Node 3] Empty question received.")
        return {
            "validation_logs": [{
                "attempt_number": state.get("current_attempt", 1),
                "layer": "grounding",
                "score_or_verdict": "fail (empty_question)",
                "feedback": "Soal kosong.",
                "aspect_evaluations": None,
                "auto_pass": False,
                "verdict": "fail",
            }],
            "failed_stage": "generation",
        }

    attempt = state.get("current_attempt", 1)
    retrieved = state.get("retrieved_chunks", [])
    source_texts = [c["text"] for c in retrieved]

    q_text = q.get("question", "")
    ans_text = q.get("answer", "")
    grounding_evidence = q.get("grounding_evidence", "")
    logger.info("[LangGraph Node 3] grounding_validation Fast-Reject (attempt %d) for: '%s'", attempt, q_text[:60])

    # Pre-check: Reject reflective questions immediately
    if is_reflective_question(q_text):
        logger.warning("[Node 3] Reflective question detected in pre-check: '%s'", q_text[:60])
        log_entry = {
            "attempt_number": attempt,
            "layer": "pre_check",
            "score_or_verdict": "fail (reflective_pattern)",
            "feedback": "Soal bersifat reflektif / meta-learning. Ganti dengan fakta/teori/konsep konkret dari buku.",
            "aspect_evaluations": None,
            "auto_pass": False,
            "verdict": "fail",
        }
        return {"validation_logs": [log_entry], "failed_stage": "generation"}

    grounding_res = compute_grounding_evidence_score(
        question_text=q_text,
        answer_text=ans_text,
        grounding_evidence=grounding_evidence,
        fallback_chunks=source_texts,
        dense_idx=dense_idx,
    )
    g_score = grounding_res["score"]
    fast_reject_thr = getattr(settings, "FAST_REJECT_THRESHOLD", 0.40)

    # Fast-Reject check: If similarity is severely low (< 0.40), reject without wasting tokens on LLM Judge
    if g_score < fast_reject_thr:
        logger.info("[Node 3] Grounding FAST-REJECT (score=%.3f < %.2f) -> route to self-refinement", g_score, fast_reject_thr)
        log_entry = {
            "attempt_number": attempt,
            "layer": "grounding",
            "score_or_verdict": f"fail (fast_reject score={g_score:.3f})",
            "feedback": f"Grounding similarity sangat rendah ({g_score:.3f} < {fast_reject_thr:.2f}). Jawaban tidak selaras dengan materi teks buku.",
            "aspect_evaluations": json.dumps({"grounding_similarity": g_score, "target": grounding_res["target"]}, ensure_ascii=False),
            "auto_pass": False,
            "verdict": "fail",
        }
        return {
            "current_question": q,
            "validation_logs": [log_entry],
            "failed_stage": "generation",
        }

    # Lolos Fast-Reject -> Lanjutkan ke LLM Judge (Layer 2) untuk evaluasi pedagogis menyeluruh
    logger.info("[Node 3] Grounding passed Fast-Reject (score=%.3f >= %.2f) -> proceeding to LLM Judge", g_score, fast_reject_thr)
    log_entry = {
        "attempt_number": attempt,
        "layer": "grounding",
        "score_or_verdict": f"pass (score={g_score:.3f})",
        "feedback": f"Lolos Fast-Reject (similarity={g_score:.3f}). Diteruskan ke LLM-as-Judge.",
        "aspect_evaluations": json.dumps({"grounding_similarity": g_score, "target": grounding_res["target"]}, ensure_ascii=False),
        "auto_pass": False,
        "verdict": "pass",
    }
    return {
        "current_question": q,
        "validation_logs": [log_entry],
        "failed_stage": "none",
    }


async def llm_judge_evaluation(state: AQGState) -> dict[str, Any]:
    """
    Node 4 (Layer 2): Evaluate question using LLM-as-Judge across 6 dimensions:
    grounding, bloom_adherence, bahasa, answerability, answer_alignment, rubric_alignment.
    """
    logger.info("[LangGraph Node 4] llm_judge_evaluation started")

    q = state.get("current_question", {})
    attempt = state.get("current_attempt", 1)
    retrieved = state.get("retrieved_chunks", [])
    source_texts = [c["text"] for c in retrieved]
    context_str = "\n".join(source_texts)[:2000]

    judge_model = get_chat_model(is_judge=True, temperature=0.05)
    target_bloom = q.get("bloom_level") or state.get("bloom_level") or "C2-Memahami"

    judge_eval, judge_trace = await asyncio.to_thread(
        run_llm_judge,
        judge_model=judge_model,
        retrieved_context=context_str,
        grounding_evidence=q.get("grounding_evidence", ""),
        question=q.get("question", ""),
        expected_answer=q.get("answer", ""),
        explanation=q.get("explanation", ""),
        target_bloom_level=target_bloom,
        attempt=attempt,
    )

    verdict = judge_eval.overall.lower().strip()
    failed_stage = judge_eval.failed_stage.lower().strip() if verdict != "pass" else "none"

    logger.info("[Node 4] LLM Judge overall='%s', failed_stage='%s'", verdict, failed_stage)

    if verdict == "pass":
        q["status"] = "final"
        q["refinement_count"] = attempt - 1

    feedback_parts = []
    for aspect_name in ["grounding", "bloom_adherence", "bahasa", "answerability", "answer_alignment"]:
        asp: Any = getattr(judge_eval, aspect_name, None)
        if asp and getattr(asp, "status", "") == "fail":
            feedback_parts.append(f"[{aspect_name.upper()}] {asp.feedback}")

    full_feedback = " ; ".join(feedback_parts) if feedback_parts else "Semua aspek evaluasi juri lolos."

    log_entry = {
        "attempt_number": attempt,
        "layer": "judge",
        "score_or_verdict": f"{verdict} (failed_stage={failed_stage})",
        "feedback": full_feedback,
        "aspect_evaluations": json.dumps(judge_eval.model_dump(), ensure_ascii=False),
        "auto_pass": False,
        "verdict": verdict,
    }

    # Append trace
    curr_traces = list(state.get("stage_traces", []))
    curr_traces.append(judge_trace.model_dump())
    q["stage_traces"] = curr_traces

    return {
        "current_question": q,
        "validation_logs": [log_entry],
        "failed_stage": failed_stage,
        "judge_evaluation": judge_eval.model_dump(),
        "stage_traces": curr_traces,
    }


async def self_refinement(state: AQGState) -> dict[str, Any]:
    """
    Node 5: Smart Self-Refinement Router:
    - If failed_stage == "planning" -> Refinement Prompt B (re-plans Bloom & Blueprint) -> re-generates.
    - If failed_stage == "generation" (default) -> Refinement Prompt A (repairs wording/grounding/explanation).
    """
    attempt = state.get("current_attempt", 1) + 1
    max_attempts = state.get("max_attempts", 3)
    q = state.get("current_question", {})
    logs = state.get("validation_logs", [])
    last_feedback = logs[-1].get("feedback", "Perbaiki soal agar lebih konkret.") if logs else "Perbaiki soal."
    failed_stage = state.get("failed_stage", "generation")

    logger.info(
        "[LangGraph Node 5] self_refinement attempt %d/%d (failed_stage='%s')",
        attempt, max_attempts, failed_stage,
    )

    if attempt > max_attempts:
        logger.warning("[Node 5] Max attempts reached. Marking question as 'needs_review'.")
        q["status"] = "needs_review"
        q["refinement_count"] = max_attempts
        return {"current_question": q, "current_attempt": attempt}

    chat_model = get_chat_model(is_judge=False, temperature=0.2)
    retrieved = state.get("retrieved_chunks", [])
    context_str = "\n".join([c["text"] for c in retrieved])[:2500]

    curr_traces = list(state.get("stage_traces", []))
    target_bloom = q.get("bloom_level") or state.get("bloom_level") or "C2-Memahami"

    c_analysis = ContentAnalysis.model_validate(q.get("content_analysis", state.get("content_analysis", {})))
    cog_plan = CognitivePlan.model_validate(q.get("cognitive_plan", state.get("cognitive_plan", {})))
    q_blueprint = QuestionBlueprint.model_validate(q.get("question_blueprint", state.get("question_blueprint", {})))

    if failed_stage == "planning":
        logger.info("[Node 5] Executing Refinement Prompt B (Planning level redesign)...")
        judge_eval_data = state.get("judge_evaluation", {})
        detected_level = judge_eval_data.get("bloom_adherence", {}).get("detected_level", "Mismatch")

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

        # Re-run Stage 3 Blueprint with new cognitive plan
        new_blueprint, t_bp = await asyncio.to_thread(
            run_stage3_question_blueprint, chat_model, c_analysis, new_plan, attempt=attempt
        )
        curr_traces.append(t_bp.model_dump())

        # Re-run Stage 4 Generation
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

        q["question"] = new_pkg.question
        q["answer"] = new_pkg.expected_answer
        q["explanation"] = new_pkg.explanation or q.get("explanation", "")
        q["answer_elements"] = []
        q["rubric"] = []
        q["grounding_evidence"] = new_pkg.grounding_evidence or new_blueprint.grounding_evidence
        q["cognitive_plan"] = new_plan.model_dump()
        q["question_blueprint"] = new_blueprint.model_dump()

    else:
        logger.info("[Node 5] Executing Refinement Prompt A (Generation level repair)...")
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

        q["question"] = new_pkg.question
        q["answer"] = new_pkg.expected_answer
        q["explanation"] = new_pkg.explanation or q.get("explanation", "")
        q["answer_elements"] = []
        q["rubric"] = []
        q["grounding_evidence"] = new_pkg.grounding_evidence or q_blueprint.grounding_evidence

    q["stage_traces"] = curr_traces
    return {
        "current_question": q,
        "current_attempt": attempt,
        "stage_traces": curr_traces,
    }


def _prune_stage_traces_for_db(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prune overly large prompt strings from trace records to prevent SQLite database bloat."""
    pruned_list = []
    for tr in traces:
        t_copy = tr.copy() if isinstance(tr, dict) else tr
        if isinstance(t_copy, dict):
            if "prompt_sent" in t_copy and isinstance(t_copy["prompt_sent"], str) and len(t_copy["prompt_sent"]) > 1000:
                t_copy["prompt_sent"] = t_copy["prompt_sent"][:1000] + "... [truncated for storage]"
            if "raw_response" in t_copy and isinstance(t_copy["raw_response"], str) and len(t_copy["raw_response"]) > 1500:
                t_copy["raw_response"] = t_copy["raw_response"][:1500] + "... [truncated for storage]"
        pruned_list.append(t_copy)
    return pruned_list


def persist_questions(state: AQGState) -> dict[str, Any]:
    """Node 6: Save validated/finalized question, full prompt traces, quality warnings, and validation logs to DB."""
    logger.info("[LangGraph Node 6] persist_questions started")
    q = state.get("current_question", {})
    if not q or not q.get("question"):
        logger.warning("[Node 6] Empty question object, skipping DB insert.")
        next_idx = state.get("current_q_index", 0) + 1
        raw_qs = state.get("raw_questions", [])
        next_q = raw_qs[next_idx] if next_idx < len(raw_qs) else {}
        return {
            "finalized_questions": [],
            "current_q_index": next_idx,
            "current_question": next_q,
            "current_attempt": 1,
            "validation_logs": [],
            "stage_traces": next_q.get("stage_traces", []),
        }

    session_id = state["session_id"]
    source_chunk_ids = state.get("source_chunk_ids", [])
    logs = state.get("validation_logs", [])
    raw_qs = state.get("raw_questions", [])
    current_idx = state.get("current_q_index", 0)
    stage_traces = q.get("stage_traces", state.get("stage_traces", []))

    q_id = str(uuid.uuid4())
    q["id"] = q_id

    # Format source reference
    source_ref = q.get("source_reference") or "Materi Buku"
    explanation = q.get("explanation") or f"Penjelasan berdasarkan materi {q.get('knowledge_point', '')}."
    q["source_reference"] = source_ref
    q["explanation"] = explanation

    # Quality warnings heuristics check
    quality_issues = validate_answer_quality(q)
    quality_warnings_json = json.dumps(quality_issues, ensure_ascii=False) if quality_issues else None

    rubric_json = json.dumps(q.get("rubric", []), ensure_ascii=False)
    answer_elements_json = json.dumps(q.get("answer_elements", []), ensure_ascii=False)
    prompt_traces_json = json.dumps(_prune_stage_traces_for_db(stage_traces), ensure_ascii=False)

    primary_cid = q.get("chunk_id")
    if primary_cid:
        ordered_chunk_ids = [primary_cid] + [cid for cid in source_chunk_ids if cid != primary_cid]
    else:
        ordered_chunk_ids = source_chunk_ids

    with get_session() as db:
        db_question = Question(
            id=q_id,
            session_id=session_id,
            chunk_ids=json.dumps(ordered_chunk_ids, ensure_ascii=False),
            question_type=q.get("question_type", "esai"),
            question_text=q.get("question", ""),
            options=json.dumps(q.get("options", {}), ensure_ascii=False) if q.get("options") else None,
            answer_key=q.get("answer", ""),
            explanation=explanation,
            source_reference=source_ref,
            bloom_level=q.get("bloom_level", state.get("bloom_level") or "C2-Memahami"),
            status=q.get("status", "final"),
            refinement_count=q.get("refinement_count", 0),
            rubric=rubric_json,
            answer_elements=answer_elements_json,
            grounding_evidence=q.get("grounding_evidence", ""),
            knowledge_point=q.get("knowledge_point", ""),
            prompt_traces=prompt_traces_json,
            quality_warnings=quality_warnings_json,
        )
        db.add(db_question)

        # Save validation logs for this question
        for log_item in logs:
            db_log = ValidationLog(
                question_id=q_id,
                attempt_number=log_item.get("attempt_number", 1),
                layer=log_item.get("layer", "grounding"),
                score_or_verdict=log_item.get("score_or_verdict", ""),
                feedback=log_item.get("feedback", ""),
                aspect_evaluations=log_item.get("aspect_evaluations"),
            )
            db.add(db_log)

        db.commit()
        logger.info(
            "[Node 6] Persisted multi-stage question id='%s' (status='%s', traces=%d) to DB.",
            q_id, q.get("status"), len(stage_traces),
        )

    next_idx = current_idx + 1
    next_q = raw_qs[next_idx] if next_idx < len(raw_qs) else {}

    return {
        "finalized_questions": [q],
        "current_q_index": next_idx,
        "current_question": next_q,
        "current_attempt": 1,
        "validation_logs": [],
        "stage_traces": next_q.get("stage_traces", []),
        "content_analysis": next_q.get("content_analysis", {}),
        "cognitive_plan": next_q.get("cognitive_plan", {}),
        "question_blueprint": next_q.get("question_blueprint", {}),
    }
