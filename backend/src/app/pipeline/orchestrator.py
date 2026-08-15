import asyncio
import uuid
import json
import logging
import time
import re
from typing import Optional, List, Dict, Any

from app.config import get_settings
from app.db.engine import get_session
from app.db.models import Chunk, Question
from app.chat.state_manager import ChatStateManager
from app.retrieval.hybrid_search import HybridSearch
from app.generation.question_generator import generate_questions
from app.validation.refinement_loop import refine_question
from app.pipeline.service import get_pipeline_service

logger = logging.getLogger(__name__)

# Kategori chunk PAC yang boleh dijadikan sumber konteks soal
_ALLOWED_CHUNK_CATEGORIES = {"KONSEP", "NARASI"}


def extract_chapter_number(chapter_str: str) -> str | None:
    """Extract chapter number or identifier (e.g. '2' from 'Bab 2', '2', 'Bab 2: Tarik dan Embuskan')."""
    if not chapter_str:
        return None
    match = re.search(r'\b(?:Bab|Chapter|Unit|Pembelajaran|Modul)?\s*([\d]+|[IVXLCDM]+)\b', str(chapter_str), re.IGNORECASE)
    if match:
        val = match.group(1).upper()
        roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'}
        return roman_map.get(val, val)
    return None


def _sanitize_retrieval_query(user_prompt: str) -> str:
    """Clean user prompt from meta generation intent words to extract pure topic keywords for search."""
    if not user_prompt:
        return ""
    text = user_prompt.lower()
    # Remove numbers preceding "soal" or "pertanyaan", e.g., "5 soal" -> ""
    text = re.sub(r'\b\d+\s*(?:soal|pertanyaan)\b', '', text, flags=re.IGNORECASE)
    # Remove meta-words and instructions
    stop_meta = [
        r'\bbuatkan\b', r'\bbuat\b', r'\bbikin\b', r'\bgenerate\b', r'\bberikan\b', r'\bminta\b', r'\btolong\b',
        r'\bsoal\b', r'\bpertanyaan\b', r'\blatihan\b', r'\btugas\b', r'\bujicoba\b',
        r'\bc[1-6]\b', r'\besai\b', r'\bisian\s*singkat\b', r'\bisian\b', r'\bpilihan\s*ganda\b',
        r'\bdong\b', r'\bya\b', r'\bsebanyak\b', r'\bjumlah\b'
    ]
    for pattern in stop_meta:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # Clean multi-spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_exercise_or_instruction_chunk(chunk_text: str) -> bool:
    """Detect if chunk contains textbook exercise questions, assignment prompts, or summary questions."""
    if not chunk_text:
        return False
    text_lower = chunk_text.lower()

    # Direct exercise/assignment phrase triggers
    exercise_phrases = [
        "menjawab pertanyaan", "pertanyaan berikut", "soal berikut",
        "rangkuman dengan menjawab", "buat rangkuman dengan",
        "tugas individu", "tugas kelompok", "latihan soal", "uji kompetensi",
        "jawablah pertanyaan", "pilihlah jawaban", "isilah titik-titik"
    ]
    if any(phrase in text_lower for phrase in exercise_phrases):
        return True

    # Detect multi-question sub-item patterns (e.g., "a. Tuliskan...", "b. Jelaskan...", "c. Buatkan...")
    sub_questions = re.findall(r'[a-e1-9][\.\)]\s*(tuliskan|jelaskan|sebutkan|buatlah|buatkan|isilah|urutkan|pasangkan|bagaimana|mengapa|apa)', text_lower)
    if len(sub_questions) >= 2 or ("menjawab pertanyaan" in text_lower and len(sub_questions) >= 1):
        return True

    # High frequency of question marks combined with imperative question words
    q_mark_count = text_lower.count('?')
    if q_mark_count >= 2:
        # Check if it lacks explanatory concept definitions (e.g. adalah, merupakan, yaitu, fungsi, proses)
        if not re.search(r'\b(adalah|merupakan|yaitu|disebut|fungsi|proses|sistem|organ)\b', text_lower):
            return True

    return False


def _deduplicate_questions(questions: list[dict], threshold: float = 0.70) -> list[dict]:
    """Remove near-duplicate questions using Jaccard similarity on question text tokens."""
    def tokenize(text: str) -> set:
        return set(re.findall(r'\w+', text.lower()))

    def jaccard(a: set, b: set) -> float:
        union = a | b
        return len(a & b) / len(union) if union else 0.0

    unique: list[dict] = []
    for candidate in questions:
        cand_tokens = tokenize(candidate.get("question", ""))
        is_duplicate = False
        for existing in unique:
            sim = jaccard(cand_tokens, tokenize(existing.get("question", "")))
            if sim >= threshold:
                logger.warning(
                    "Duplicate removed (Jaccard=%.2f): '%s'",
                    sim, candidate.get("question", "")[:80]
                )
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(candidate)

    logger.info(
        "Deduplication: %d -> %d questions (threshold=%.2f)",
        len(questions), len(unique), threshold
    )
    return unique


async def run_aqg_pipeline(
    session_id: str,
    document_id: str,
    user_prompt: str,
    num_questions: int = 5,
    chapter: Optional[str] = None,
    bloom_level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run the complete AQG RAG + Generation + 2-Layer Refinement pipeline with parallel optimization."""
    settings = get_settings()
    service = get_pipeline_service()
    pipeline_start = time.time()
    
    logger.info("=" * 60)
    logger.info("Starting AQG Pipeline for session_id='%s', doc_id='%s'", session_id, document_id)
    logger.info("  Params: num_questions=%d, chapter=%s, bloom_level=%s",
                num_questions, chapter or '(all)', bloom_level or '(all)')

    # Step 1: Load document chunks from DB
    with get_session() as db:
        chunks_db = db.query(Chunk).filter(Chunk.document_id == document_id).all()
        if not chunks_db:
            logger.error("No chunks found in database for document_id='%s'", document_id)
            raise ValueError(f"Dokumen dengan ID '{document_id}' tidak memiliki chunk materi.")
        
        chunks_data = [
            {
                "id": c.id,
                "text": c.text,
                "metadata": {
                    "document_id": c.document_id,
                    "category": c.category,
                    "chapter": c.chapter or "",
                    "section_heading": c.section_heading or "",
                }
            }
            for c in chunks_db
        ]
        
        manager = ChatStateManager(session_id, db)
        chat_history = manager.get_context_summary()

    logger.info("Loaded %d chunks for document_id='%s'", len(chunks_data), document_id)

    # Filter candidate chunks strictly by requested chapter if chapter parameter is provided
    if chapter:
        target_ch_num = extract_chapter_number(chapter)
        if target_ch_num:
            filtered_chunks = [
                c for c in chunks_data
                if extract_chapter_number(c["metadata"].get("chapter", "")) == target_ch_num
            ]
            if filtered_chunks:
                logger.info("Filtered %d candidate chunks strictly for Chapter %s (out of %d total)",
                            len(filtered_chunks), target_ch_num, len(chunks_data))
                chunks_data = filtered_chunks
            else:
                logger.warning("No chunks matched chapter_number=%s in metadata. Searching all chunks.", target_ch_num)

    # Filter chunks by pedagogical category — only KONSEP and NARASI are used as question sources
    before_cat = len(chunks_data)
    cat_filtered = [
        c for c in chunks_data
        if c["metadata"].get("category", "KONSEP") in _ALLOWED_CHUNK_CATEGORIES
    ]
    if cat_filtered:
        logger.info(
            "Category filter: kept %d/%d chunks (removed EVALUASI/INSTRUKSI categories)",
            len(cat_filtered), before_cat
        )
        chunks_data = cat_filtered
    else:
        logger.warning(
            "Category filter would remove ALL %d chunks — keeping originals as fallback", before_cat
        )

    # Step 2: Build BM25 index & Hybrid Search (using cached BM25 index)
    logger.info("Step 1/4: Hybrid Retrieval (Dense ChromaDB + Sparse BM25)...")
    sparse_index = service.create_sparse_index(chunks_data, cache_key=f"{document_id}_{len(chunks_data)}")
    hybrid = HybridSearch(
        dense_index=service.dense_index,
        sparse_index=sparse_index,
        dense_weight=settings.HYBRID_DENSE_WEIGHT,
        sparse_weight=settings.HYBRID_SPARSE_WEIGHT
    )
    
    clean_query = _sanitize_retrieval_query(user_prompt)
    retrieval_query = clean_query if clean_query else user_prompt
    if chapter:
        retrieval_query += f" Bab {chapter}"
        
    logger.info("Retrieval query: '%s' (sanitized from raw user_prompt='%s')", retrieval_query, user_prompt)
    retrieved_chunks = hybrid.search(query=retrieval_query, top_k=settings.RETRIEVAL_TOP_K * 2)
    
    if not retrieved_chunks:
        logger.warning("Hybrid search returned 0 chunks, falling back to top %d document chunks",
                       settings.RETRIEVAL_TOP_K)
        retrieved_chunks = chunks_data[:settings.RETRIEVAL_TOP_K * 2]
        
    # Apply anti-exercise & anti-instruction runtime filter
    filtered_retrieved = [
        c for c in retrieved_chunks
        if not _is_exercise_or_instruction_chunk(c["text"])
    ]
    if filtered_retrieved:
        logger.info(
            "Anti-exercise filter: kept %d/%d context chunks (removed textbook exercise/instruction blocks)",
            len(filtered_retrieved), len(retrieved_chunks)
        )
        retrieved_chunks = filtered_retrieved[:settings.RETRIEVAL_TOP_K]
    else:
        logger.warning(
            "Anti-exercise filter removed all %d candidate chunks — falling back to top %d chunks",
            len(retrieved_chunks), settings.RETRIEVAL_TOP_K
        )
        retrieved_chunks = retrieved_chunks[:settings.RETRIEVAL_TOP_K]

    source_context_texts = [c["text"] for c in retrieved_chunks]
    source_chunk_ids = [c["id"] for c in retrieved_chunks]
    logger.info("Final context: selected %d clean context chunks for LLM question generation", len(source_context_texts))

    # Step 3: Call Question Generator LLM with Over-generation (request n + 2 questions for candidate selection)
    over_gen_count = num_questions + 2
    logger.info("Step 2/4: Generating raw candidate questions via LLM (%s, over_gen=%d)...",
                settings.LLM_GENERATOR_MODEL, over_gen_count)
    raw_questions = await generate_questions(
        ollama_client=service.ollama_client,
        model_name=settings.LLM_GENERATOR_MODEL,
        context_chunks=source_context_texts,
        num_questions=over_gen_count,
        chapter=chapter,
        bloom_level=bloom_level,
        chat_history=chat_history
    )
    
    if not raw_questions:
        logger.error("LLM failed to generate questions")
        raise RuntimeError("Gagal menghasilkan soal dari model LLM. Silakan coba kembali.")

    # Deduplication & selecting top candidates up to num_questions
    raw_questions = _deduplicate_questions(raw_questions, threshold=0.70)
    if not raw_questions:
        logger.error("All generated questions were duplicates after deduplication")
        raise RuntimeError("Semua soal yang dihasilkan terduplikasi. Silakan coba kembali.")

    raw_questions = raw_questions[:num_questions]

    logger.info("Step 3/4: Processing parallel 2-layer validation & refinement for %d questions...", len(raw_questions))
    
    semaphore = asyncio.Semaphore(3)

    async def _refine_and_save_question(idx: int, raw_q: dict) -> dict:
        async with semaphore:
            q_id = str(uuid.uuid4())
            logger.info("Refining Question %d/%d (q_id='%s')...", idx, len(raw_questions), q_id)
            
            with get_session() as db:
                final_q = await refine_question(
                    ollama_client=service.ollama_client,
                    generator_model=settings.LLM_GENERATOR_MODEL,
                    judge_model=settings.LLM_JUDGE_MODEL,
                    initial_question=raw_q,
                    source_chunks=source_context_texts,
                    embedding_model=service.dense_index.model,
                    max_attempts=settings.MAX_REFINEMENT_ATTEMPTS,
                    grounding_threshold=settings.GROUNDING_THRESHOLD,
                    db_session=db,
                    question_id=q_id,
                    auto_pass_threshold=settings.GROUNDING_AUTO_PASS_THRESHOLD,
                )
                
                opts_raw = final_q.get("options")
                options_json = json.dumps(opts_raw, ensure_ascii=False) if opts_raw else "{}"
                chunk_ids_json = json.dumps(source_chunk_ids, ensure_ascii=False)
                
                source_ref = final_q.get("source_reference")
                if not source_ref and retrieved_chunks:
                    refs = []
                    for c in retrieved_chunks:
                        meta = c.get("metadata", {})
                        chap = meta.get("chapter", "")
                        sec = meta.get("section_heading", "")
                        ref_str = f"{chap} - {sec}".strip(" -")
                        if ref_str and ref_str not in refs:
                            refs.append(ref_str)
                    source_ref = " | ".join(refs) if refs else "Bab Materi Buku"

                explanation_text = final_q.get("explanation", "Penjelasan berdasarkan konteks materi buku.")

                db_question = Question(
                    id=q_id,
                    session_id=session_id,
                    chunk_ids=chunk_ids_json,
                    question_type=final_q.get("question_type", "esai"),
                    question_text=final_q.get("question", ""),
                    options=options_json,
                    answer_key=final_q.get("answer", ""),
                    explanation=explanation_text,
                    source_reference=source_ref,
                    bloom_level=final_q.get("bloom_level", bloom_level or "C2-Memahami"),
                    status=final_q.get("status", "final"),
                    refinement_count=final_q.get("refinement_count", 0)
                )
                db.add(db_question)
                db.commit()
                
                final_q["id"] = q_id
                final_q["explanation"] = explanation_text
                final_q["source_reference"] = source_ref
                logger.info("Question %d saved to DB (q_id='%s', status='%s', refinements=%d)",
                            idx, q_id, final_q.get("status"), final_q.get("refinement_count", 0))
                return final_q

    tasks = [_refine_and_save_question(idx, raw_q) for idx, raw_q in enumerate(raw_questions, 1)]
    finalized_questions = list(await asyncio.gather(*tasks))

    elapsed = time.time() - pipeline_start
    logger.info("AQG Pipeline COMPLETED in %.2fs. Created %d finalized questions.",
                elapsed, len(finalized_questions))
    logger.info("=" * 60)
    
    return finalized_questions

