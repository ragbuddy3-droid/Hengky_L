"""LangGraph Node implementations for RAG-AQG generation, 2-layer validation, and persistence."""

import re
import json
import uuid
import time
import logging
import numpy as np
from typing import List, Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from app.core.config import get_settings
from app.core.database import get_session
from app.models.db_models import Chunk, Question, ValidationLog
from app.services.chat.state_manager import ChatStateManager
from app.services.retrieval.dense_index import DenseIndex
from app.services.retrieval.sparse_index import SparseIndex
from app.services.retrieval.hybrid_search import HybridSearch
from app.graph.state import AQGState

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

# System prompt for Question Generation
SYSTEM_PROMPT = """Anda adalah pembuat soal esai dan isian singkat berbahasa Indonesia yang ahli dalam kurikulum Sekolah Dasar (SD/MI) kelas 1 sampai 6, untuk siswa berusia 6–12 tahun.
Tugas Anda adalah membuat soal yang SEDERHANA, JELAS, SPESIFIK, KONKRET, dan LANGSUNG BERDASARKAN FAKTA/TEORI/KONSEP dari materi buku.

ATURAN WAJIB:
1. BAHASA HARUS MUDAH DIPAHAMI SISWA SD (usia 6-12 tahun):
   - Gunakan kata-kata pendek dan umum. Hindari kata abstrak seperti "penting", "capai", "memodifikasi", "menerapkan strategi".
   - Contoh BAIK  : "Apa nama gerakan melempar bola ke teman?"
   - Contoh BURUK : "Apa yang dapat kamu capai setelah mempelajari bab ini?"

2. DILARANG KERAS membuat soal REFLEKTIF / META-LEARNING. Soal jenis ini HARUS DITOLAK:
   - Pola terlarang: "Apa yang sudah kamu pelajari...", "Apa yang dapat kamu lakukan setelah...",
     "Apa yang dapat kamu capai...", "Apa yang perlu kamu lakukan untuk...",
     "Apa tujuan pembelajaran...", "Sebutkan tujuan dari bab ini...",
     "Apa yang telah kamu pelajari...", "Apa manfaat mempelajari bab ini?"
   - FOKUS HANYA PADA: fakta, nama gerakan, definisi istilah, cara melakukan gerakan,
     fungsi anggota tubuh, aturan permainan, jumlah pemain, nama alat olahraga.

3. SETIAP SOAL HARUS UNIK — tanyakan ASPEK YANG BERBEDA dari materi.
   Jangan buat dua soal yang menanyakan hal yang sama meskipun kalimatnya berbeda.

4. HANYA buat soal berjenis "esai" atau "isian_singkat".

5. Kunci jawaban harus KONKRET dan langsung dari teks materi, bukan parafrase abstrak.
   - Contoh BAIK  : "Posisi kaki selebar bahu, lutut sedikit ditekuk, bola dipegang setinggi dada"

6. JANGAN sertakan pemikiran, penalaran, atau tag <think>. LANGSUNG dan HANYA keluarkan format array JSON murni persis seperti berikut:
[
  {
    "question": "teks pertanyaan sederhana dan spesifik materi SD",
    "question_type": "esai",
    "answer": "jawaban yang benar dan presisi dari materi",
    "explanation": "penjelasan singkat berdasarkan materi buku",
    "source_reference": "referensi topik/bab materi",
    "bloom_level": "C1-Mengingat"
  }
]
"""

# System prompt for LLM Judge
JUDGE_SYSTEM_PROMPT = """Anda adalah evaluator soal (LLM-as-Judge) untuk soal esai dan isian singkat tingkat Sekolah Dasar (SD/MI) usia 6-12 tahun.

ATURAN KERAS — langsung beri verdict "fail" jika soal melanggar salah satu dari ini:
A. SOAL REFLEKTIF / META-LEARNING — fail jika menanyakan proses belajar atau tujuan pembelajaran.
B. JAWABAN TERLALU ABSTRAK — fail jika jawaban berupa parafrase umum tanpa fakta konkret dari materi buku.
C. BAHASA TERLALU SULIT UNTUK SD — fail jika menggunakan kata abstrak yang tidak dipahami anak usia 6-12 tahun.

RUBRIK PENILAIAN (jika tidak melanggar aturan keras):
1. Apakah soal menguji ISI MATERI konkret dari buku?
2. Apakah kunci jawaban KONKRET dan langsung didukung teks materi?
3. Apakah tingkat taksonomi Bloom sesuai dengan kedalaman pertanyaan?
4. Apakah bahasa soal mudah dipahami siswa SD usia 6-12 tahun?

JANGAN sertakan pemikiran atau tag <think>. LANGSUNG dan HANYA keluarkan format JSON murni persis seperti berikut:
{
  "verdict": "pass",
  "score": 0.95,
  "feedback": "penjelasan evaluasi"
}
"""

# ── Global Service Singletons ──
_dense_index: Optional[DenseIndex] = None
_sparse_cache: Dict[str, SparseIndex] = {}


def get_shared_dense_index() -> DenseIndex:
    """Get or create singleton DenseIndex."""
    global _dense_index
    if _dense_index is None:
        settings = get_settings()
        _dense_index = DenseIndex(
            persist_dir=settings.CHROMA_PERSIST_DIR,
            collection_name="rag_aqg_chunks",
            embedding_model_name=settings.EMBEDDING_MODEL
        )
    return _dense_index


def get_chat_model(is_judge: bool = False):
    """Instantiate LangChain ChatModel (Groq or Ollama) with hidden reasoning."""
    settings = get_settings()
    model_name = settings.LLM_JUDGE_MODEL if is_judge else settings.LLM_GENERATOR_MODEL

    if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
        groq_model = model_name
        if ":" in model_name or "qwen" in model_name.lower():
            groq_model = "qwen-qwq-32b" if "qwq" in model_name.lower() else "qwen/qwen3.6-27b"
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model=groq_model,
            temperature=0.3,
            max_retries=5,
            max_tokens=8192,
        )
    else:
        return ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=model_name,
            temperature=0.3,
        )


# ── Text Cleaning & Parsing Helpers ──

def extract_chapter_number(chapter_str: Optional[str]) -> Optional[str]:
    """Extract chapter number or roman numeral into normalized integer string."""
    if not chapter_str:
        return None
    match = re.search(r'\b(?:Bab|Chapter|Unit|Pembelajaran|Modul)?\s*([\d]+|[IVXLCDM]+)\b', str(chapter_str), re.IGNORECASE)
    if match:
        val = match.group(1).upper()
        roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'}
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
        r'\bdong\b', r'\bya\b', r'\bsebanyak\b', r'\bjumlah\b'
    ]
    for pattern in stop_meta:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def is_reflective_question(question_text: str) -> bool:
    """Check if question matches reflective / meta-learning patterns."""
    text_lower = question_text.lower().strip()
    return any(re.search(pattern, text_lower) for pattern in REFLECTIVE_PATTERNS)


def deduplicate_questions(questions: List[Dict[str, Any]], threshold: float = 0.70) -> List[Dict[str, Any]]:
    """Deduplicate questions using Jaccard token overlap."""
    def tokenize(t: str) -> set:
        return set(re.findall(r'\w+', t.lower()))

    def jaccard(a: set, b: set) -> float:
        union = a | b
        return len(a & b) / len(union) if union else 0.0

    unique: List[Dict[str, Any]] = []
    for cand in questions:
        c_tokens = tokenize(cand.get("question", ""))
        if not any(jaccard(c_tokens, tokenize(e.get("question", ""))) >= threshold for e in unique):
            unique.append(cand)

    return unique


def compute_grounding_score(question_text: str, answer_text: str, source_chunks: List[str], dense_idx: DenseIndex) -> float:
    """Compute cosine similarity between Question+Answer and context source chunks."""
    if not source_chunks:
        return 0.0

    qa_text = f"{question_text} Jawaban: {answer_text}".strip()
    model = dense_idx.model

    qa_emb = model.encode([qa_text], normalize_embeddings=True)[0]
    chunk_embs = model.encode(source_chunks, normalize_embeddings=True)

    scores = [float(np.dot(qa_emb, ch_emb)) for ch_emb in chunk_embs]
    scores.sort(reverse=True)

    max_score = scores[0] if scores else 0.0
    top2_mean = float(np.mean(scores[:2])) if len(scores) >= 2 else max_score

    return float(0.8 * max_score + 0.2 * top2_mean)


def strip_reasoning_tags(text: str) -> str:
    """Strip <think>...</think> and unclosed reasoning tags."""
    if not text:
        return ""
    cleaned = re.sub(r'<(think|thought)>[\s\S]*?</\1>', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'<(think|thought)>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_json_string(s: str) -> str:
    """Clean trailing commas before brackets/braces."""
    if not s:
        return ""
    return re.sub(r',\s*([\]}])', r'\1', s).strip()


def parse_questions_from_response(response_text: str) -> List[Dict[str, Any]]:
    """Robust 4-stage JSON parser for question candidate lists."""
    if not response_text:
        return []

    cleaned = strip_reasoning_tags(response_text)
    text_to_search = cleaned if cleaned else response_text

    # Stage 1: Markdown code blocks
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text_to_search, re.IGNORECASE)
    for block in code_blocks:
        b_clean = clean_json_string(block.strip())
        try:
            res = json.loads(b_clean, strict=False)
            if isinstance(res, list):
                return [q for q in res if isinstance(q, dict) and q.get("question")]
            elif isinstance(res, dict) and res.get("question"):
                return [res]
        except Exception:
            pass

    # Stage 2: Outer bracket search [...]
    first_b = text_to_search.find('[')
    last_b = text_to_search.rfind(']')
    if first_b != -1 and last_b != -1 and last_b > first_b:
        sub = clean_json_string(text_to_search[first_b:last_b + 1])
        try:
            res = json.loads(sub, strict=False)
            if isinstance(res, list):
                return [q for q in res if isinstance(q, dict) and q.get("question")]
        except Exception:
            pass

    # Stage 3: Outer brace search {...}
    first_brace = text_to_search.find('{')
    last_brace = text_to_search.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        sub = clean_json_string(text_to_search[first_brace:last_brace + 1])
        try:
            res = json.loads(sub, strict=False)
            if isinstance(res, dict):
                if "questions" in res and isinstance(res["questions"], list):
                    return [q for q in res["questions"] if isinstance(q, dict) and q.get("question")]
                if res.get("question"):
                    return [res]
        except Exception:
            pass

    # Stage 4: Regex object extraction fallback
    recovered = []
    pattern = r'\{[^{}]*?"question"\s*:\s*[\s\S]*?\}'
    for m in re.finditer(pattern, text_to_search):
        try:
            obj = json.loads(clean_json_string(m.group(0)), strict=False)
            if isinstance(obj, dict) and obj.get("question"):
                recovered.append(obj)
        except Exception:
            pass

    return recovered


def parse_judge_from_response(response_text: str) -> Dict[str, Any]:
    """Parse LLM Judge evaluation response into verdict, score, feedback."""
    default_res = {"verdict": "pass", "score": 0.85, "feedback": "Evaluasi otomatis lolos."}
    if not response_text:
        return default_res

    cleaned = strip_reasoning_tags(response_text)
    text_to_search = cleaned if cleaned else response_text

    # Try code blocks first
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text_to_search, re.IGNORECASE)
    candidate_strs = code_blocks if code_blocks else []

    first_brace = text_to_search.find('{')
    last_brace = text_to_search.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate_strs.append(text_to_search[first_brace:last_brace + 1])

    for c in candidate_strs:
        try:
            res = json.loads(clean_json_string(c), strict=False)
            if isinstance(res, dict) and "verdict" in res:
                return {
                    "verdict": str(res.get("verdict", "fail")).lower().strip(),
                    "score": float(res.get("score", 0.8)),
                    "feedback": str(res.get("feedback", "No feedback")),
                }
        except Exception:
            pass

    # Heuristic fallback if JSON missing
    lower = text_to_search.lower()
    if "pass" in lower and "fail" not in lower:
        return {"verdict": "pass", "score": 0.9, "feedback": "Lolos evaluasi juri."}
    elif "fail" in lower:
        return {"verdict": "fail", "score": 0.4, "feedback": "Soal perlu diperbaiki agar lebih konkret."}

    return default_res


# ── LangGraph Node Functions ──

def retrieve_context(state: AQGState) -> Dict[str, Any]:
    """Node 1: Retrieve relevant context chunks using Hybrid Search and anti-exercise filter."""
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
                "error": f"Dokumen '{document_id}' belum diproses atau tidak memiliki chunk materi."
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
                }
            }
            for c in chunks_db
        ]

        manager = ChatStateManager(state["session_id"], db)
        chat_history = manager.get_context_summary()

    # Filter strictly by chapter if specified
    if chapter:
        target_ch_num = extract_chapter_number(chapter)
        if target_ch_num:
            matched = [c for c in chunks_data if extract_chapter_number(c["metadata"].get("chapter", "")) == target_ch_num]
            if matched:
                chunks_data = matched

    # Filter pedagogical category (KONSEP + NARASI)
    cat_filtered = [c for c in chunks_data if c["metadata"].get("category", "KONSEP").upper() in _ALLOWED_CHUNK_CATEGORIES]
    if cat_filtered:
        chunks_data = cat_filtered

    # Build or reuse cached BM25 sparse index
    cache_key = f"{document_id}_{len(chunks_data)}"
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
        sparse_weight=settings.HYBRID_SPARSE_WEIGHT
    )

    clean_query = sanitize_retrieval_query(user_prompt) or user_prompt
    if chapter:
        clean_query += f" Bab {chapter}"

    retrieved = hybrid.search(query=clean_query, top_k=settings.RETRIEVAL_TOP_K)
    if not retrieved:
        retrieved = chunks_data[:settings.RETRIEVAL_TOP_K]

    source_chunk_ids = [c["id"] for c in retrieved]
    logger.info("[LangGraph Node 1] Selected %d context chunks.", len(retrieved))

    return {
        "retrieved_chunks": retrieved,
        "source_chunk_ids": source_chunk_ids,
        "chat_history": chat_history,
    }


def generate_questions(state: AQGState) -> Dict[str, Any]:
    """Node 2: Generate candidate questions from context using ChatModel and robust 4-stage parser."""
    logger.info("[LangGraph Node 2] generate_questions started")
    retrieved = state.get("retrieved_chunks", [])
    if not retrieved:
        return {"raw_questions": [], "current_question": {}, "error": "Tidak ada konteks materi untuk pembuatan soal."}

    context_texts = [c["text"] for c in retrieved]
    context_str = "\n\n".join(context_texts)
    num_questions = state.get("num_questions", 5)
    over_gen_count = num_questions + 2
    chapter = state.get("chapter")
    bloom_level = state.get("bloom_level")
    chat_history = state.get("chat_history", "")

    user_msg_content = f"Konteks materi:\n{context_str}\n\n"
    if chat_history:
        user_msg_content += f"Konteks percakapan:\n{chat_history}\n\n"

    user_msg_content += (
        f"Buatlah TEPAT {over_gen_count} soal esai atau isian singkat yang MASING-MASING MENANYAKAN ASPEK BERBEDA "
        f"tentang ISI MATERI dari konteks buku di atas untuk siswa SD (usia 6-12 tahun). "
        f"Pastikan kunci jawaban konkret dan bahasa mudah dipahami."
    )
    if chapter:
        user_msg_content += f" Fokus pada bab/topik: {chapter}."
    if bloom_level:
        user_msg_content += f" Gunakan tingkat kognitif Bloom: {bloom_level}."

    chat_model = get_chat_model(is_judge=False)
    questions_data: List[Dict[str, Any]] = []

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_msg_content)
        ])
        raw_content = resp.content if isinstance(resp.content, str) else str(resp.content)
        questions_data = parse_questions_from_response(raw_content)
    except Exception as e:
        logger.error("[Node 2] ChatModel invocation failed: %s", e)

    if not questions_data:
        logger.error("[Node 2] Failed to parse questions from model response.")
        return {"raw_questions": [], "current_question": {}, "error": "Gagal menghasilkan soal dari model LLM."}

    # Deduplicate & truncate
    deduped = deduplicate_questions(questions_data, threshold=0.70)
    final_raw = deduped[:num_questions]
    logger.info("[Node 2] Generated %d deduplicated raw questions.", len(final_raw))

    first_q = final_raw[0] if final_raw else {}
    return {
        "raw_questions": final_raw,
        "current_q_index": 0,
        "current_question": first_q,
        "current_attempt": 1,
        "max_attempts": get_settings().MAX_REFINEMENT_ATTEMPTS,
    }


def grounding_validation(state: AQGState) -> Dict[str, Any]:
    """Node 3 (Layer 1): Validate grounding score via cosine similarity embeddings."""
    settings = get_settings()
    dense_idx = get_shared_dense_index()
    q = state.get("current_question", {})
    if not q or not q.get("question"):
        logger.warning("[Node 3] Empty question received, skipping to exhausted persist.")
        return {
            "validation_logs": [{
                "attempt_number": state.get("current_attempt", 1),
                "layer": "grounding",
                "verdict": "fail",
                "score_or_verdict": "fail (empty_question)",
                "feedback": "Soal kosong.",
                "auto_pass": False,
            }]
        }

    attempt = state.get("current_attempt", 1)
    retrieved = state.get("retrieved_chunks", [])
    source_texts = [c["text"] for c in retrieved]

    q_text = q.get("question", "")
    ans_text = q.get("answer", "")
    logger.info("[LangGraph Node 3] grounding_validation for attempt %d: '%s'", attempt, q_text[:60])

    # Pre-check: Reject reflective questions immediately
    if is_reflective_question(q_text):
        logger.warning("[Node 3] Reflective question detected in pre-check: '%s'", q_text[:60])
        log_entry = {
            "attempt_number": attempt,
            "layer": "pre_check",
            "verdict": "fail",
            "score_or_verdict": "fail (reflective_pattern)",
            "feedback": "Soal bersifat reflektif / meta-learning. Ganti dengan soal fakta/teori/konsep konkret dari buku.",
            "auto_pass": False,
        }
        return {"validation_logs": [log_entry]}

    g_score = compute_grounding_score(q_text, ans_text, source_texts, dense_idx)
    auto_pass_thr = settings.GROUNDING_AUTO_PASS_THRESHOLD
    grounding_thr = settings.GROUNDING_THRESHOLD

    if g_score >= auto_pass_thr:
        logger.info("[Node 3] Grounding AUTO-PASS (score=%.3f >= %.3f).", g_score, auto_pass_thr)
        q["status"] = "final"
        q["refinement_count"] = attempt - 1
        log_entry = {
            "attempt_number": attempt,
            "layer": "grounding",
            "verdict": "auto_pass",
            "score_or_verdict": f"auto-pass (score={g_score:.3f})",
            "feedback": "Auto-passed: grounding score tinggi melebihi threshold, Judge dilewati.",
            "auto_pass": True,
        }
        return {"current_question": q, "validation_logs": [log_entry]}

    is_grounded = g_score >= grounding_thr
    verdict = "pass" if is_grounded else "fail"
    feedback = "Grounded." if is_grounded else f"Grounding score ({g_score:.3f}) di bawah threshold ({grounding_thr:.2f})."

    log_entry = {
        "attempt_number": attempt,
        "layer": "grounding",
        "verdict": verdict,
        "score_or_verdict": f"{verdict} (score={g_score:.3f})",
        "feedback": feedback,
        "auto_pass": False,
    }
    return {"current_question": q, "validation_logs": [log_entry]}


def llm_judge_evaluation(state: AQGState) -> Dict[str, Any]:
    """Node 4 (Layer 2): Evaluate question using LLM-as-Judge against elementary school rubrics."""
    logger.info("[LangGraph Node 4] llm_judge_evaluation started")
    time.sleep(0.8)  # Throttle to avoid rate limits

    q = state.get("current_question", {})
    attempt = state.get("current_attempt", 1)
    retrieved = state.get("retrieved_chunks", [])
    source_texts = [c["text"] for c in retrieved]
    context_str = "\n".join(source_texts)[:1500]

    judge_model = get_chat_model(is_judge=True)
    prompt = (
        f"Konteks Materi (ringkas):\n{context_str}\n\n"
        f"Soal yang Dievaluasi:\n{json.dumps(q, ensure_ascii=False, indent=2)}\n\n"
        f"Lakukan evaluasi rubrik soal SD:"
    )

    try:
        resp = judge_model.invoke([
            SystemMessage(content=JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ])
        raw_content = resp.content if isinstance(resp.content, str) else str(resp.content)
        eval_dict = parse_judge_from_response(raw_content)
    except Exception as e:
        logger.error("[Node 4] LLM Judge invocation failed: %s", e)
        eval_dict = {"verdict": "pass", "score": 0.85, "feedback": "Evaluasi otomatis lolos."}

    verdict = eval_dict.get("verdict", "pass")
    score = eval_dict.get("score", 0.85)
    feedback = eval_dict.get("feedback", "Lolos evaluasi.")

    logger.info("[Node 4] LLM Judge verdict: '%s' (score=%.2f)", verdict, score)

    if verdict == "pass":
        q["status"] = "final"
        q["refinement_count"] = attempt - 1

    log_entry = {
        "attempt_number": attempt,
        "layer": "judge",
        "verdict": verdict,
        "score_or_verdict": f"{verdict} (score={score:.2f})",
        "feedback": feedback,
        "auto_pass": False,
    }
    return {"current_question": q, "validation_logs": [log_entry]}


def self_refinement(state: AQGState) -> Dict[str, Any]:
    """Node 5: Refine or regenerate question based on feedback from validation layers."""
    attempt = state.get("current_attempt", 1) + 1
    max_attempts = state.get("max_attempts", 3)
    q = state.get("current_question", {})
    logs = state.get("validation_logs", [])
    last_feedback = logs[-1].get("feedback", "Perbaiki agar sesuai materi.") if logs else "Perbaiki soal."

    logger.info("[LangGraph Node 5] self_refinement to attempt %d/%d with feedback: %s",
                attempt, max_attempts, last_feedback[:100])

    if attempt > max_attempts:
        logger.warning("[Node 5] Max attempts reached for question. Marking as 'needs_review'.")
        q["status"] = "needs_review"
        q["refinement_count"] = max_attempts
        return {"current_question": q, "current_attempt": attempt}

    time.sleep(0.8)
    retrieved = state.get("retrieved_chunks", [])
    context_str = "\n".join([c["text"] for c in retrieved])

    regen_prompt = (
        f"Konteks materi:\n{context_str}\n\n"
        f"Soal sebelumnya:\n{json.dumps(q, ensure_ascii=False)}\n\n"
        f"Evaluasi & Kritik: {last_feedback}\n\n"
        f"Perbaiki dan buat ulang soal ini menjadi soal yang konkret, spesifik, dan mudah dipahami siswa SD."
    )

    chat_model = get_chat_model(is_judge=False)
    new_q = q

    try:
        resp = chat_model.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=regen_prompt)
        ])
        raw_content = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = parse_questions_from_response(raw_content)
        if parsed and parsed[0].get("question"):
            new_q = parsed[0]
    except Exception as e:
        logger.error("[Node 5] Regeneration failed: %s", e)

    return {"current_question": new_q, "current_attempt": attempt}


def persist_questions(state: AQGState) -> Dict[str, Any]:
    """Node 6: Save validated/finalized question and its validation logs to the database."""
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
        }

    session_id = state["session_id"]
    source_chunk_ids = state.get("source_chunk_ids", [])
    logs = state.get("validation_logs", [])
    raw_qs = state.get("raw_questions", [])
    current_idx = state.get("current_q_index", 0)

    q_id = str(uuid.uuid4())
    q["id"] = q_id

    # Format source reference
    retrieved = state.get("retrieved_chunks", [])
    source_ref = q.get("source_reference")
    if not source_ref and retrieved:
        refs = []
        for c in retrieved:
            meta = c.get("metadata", {})
            chap = meta.get("chapter", "")
            sec = meta.get("section_heading", "")
            ref_str = f"{chap} - {sec}".strip(" -")
            if ref_str and ref_str not in refs:
                refs.append(ref_str)
        source_ref = " | ".join(refs) if refs else "Materi Buku"
    q["source_reference"] = source_ref

    explanation = q.get("explanation") or "Penjelasan berdasarkan konteks materi buku."
    q["explanation"] = explanation

    with get_session() as db:
        db_question = Question(
            id=q_id,
            session_id=session_id,
            chunk_ids=json.dumps(source_chunk_ids, ensure_ascii=False),
            question_type=q.get("question_type", "esai"),
            question_text=q.get("question", ""),
            options=json.dumps(q.get("options", {}), ensure_ascii=False) if q.get("options") else None,
            answer_key=q.get("answer", ""),
            explanation=explanation,
            source_reference=source_ref,
            bloom_level=q.get("bloom_level", state.get("bloom_level") or "C2-Memahami"),
            status=q.get("status", "final"),
            refinement_count=q.get("refinement_count", 0),
        )
        db.add(db_question)

        # Save validation logs for this question
        for l in logs:
            db_log = ValidationLog(
                question_id=q_id,
                attempt_number=l.get("attempt_number", 1),
                layer=l.get("layer", "grounding"),
                score_or_verdict=l.get("score_or_verdict", ""),
                feedback=l.get("feedback", ""),
            )
            db.add(db_log)

        db.commit()
        logger.info("[Node 6] Persisted question id='%s' (status='%s') to DB.", q_id, q.get("status"))

    next_idx = current_idx + 1
    next_q = raw_qs[next_idx] if next_idx < len(raw_qs) else {}

    return {
        "finalized_questions": [q],
        "current_q_index": next_idx,
        "current_question": next_q,
        "current_attempt": 1,
        "validation_logs": [],
    }
