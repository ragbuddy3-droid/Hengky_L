"""Self-refinement orchestration."""
import asyncio
import uuid
import json
import re
import time
import logging
from datetime import datetime, timezone
from app.db.models import ValidationLog
from app.validation.grounding_score import compute_grounding_score, validate_grounding
from app.validation.llm_judge import evaluate_question
from app.generation.question_generator import SYSTEM_PROMPT, extract_json_payload, parse_questions_response

logger = logging.getLogger(__name__)

# Threshold grounding score untuk auto-pass (skip LLM Judge) — hemat 1 LLM call
GROUNDING_AUTO_PASS_THRESHOLD = 0.80
# Jeda antar panggilan LLM untuk menghindari rate limit burst
LLM_CALL_THROTTLE_SEC = 0.8


# Pola regex untuk mendeteksi soal reflektif/meta-learning secara cepat
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


def is_reflective_question(question_text: str) -> bool:
    """Return True if question matches reflective/meta-learning patterns."""
    text_lower = question_text.lower().strip()
    for pattern in REFLECTIVE_PATTERNS:
        if re.search(pattern, text_lower):
            logger.debug("Reflective pattern matched: '%s' in '%s'", pattern, text_lower[:80])
            return True
    return False



async def refine_question(
    ollama_client,
    generator_model: str,
    judge_model: str,
    initial_question: dict,
    source_chunks: list[str],
    embedding_model,
    max_attempts: int,
    grounding_threshold: float,
    db_session,
    question_id: str | None = None,
    auto_pass_threshold: float = GROUNDING_AUTO_PASS_THRESHOLD,
) -> dict:
    """Run the validation + refinement loop for a single question."""
    logger.info("="*50)
    logger.info("Starting refinement loop (question_id=%s, max_attempts=%d, grounding_threshold=%.2f)",
                question_id, max_attempts, grounding_threshold)
    q_text = initial_question.get('question', '(unknown)')[:80]
    logger.info("  Initial question: '%s...'", q_text)
    
    loop_start = time.time()
    current_question = initial_question
    context_str = "\n".join(source_chunks)

    # --- Pre-check: Fast-reject soal reflektif sebelum masuk loop validasi ---
    initial_q_text = current_question.get("question", "")
    if is_reflective_question(initial_q_text):
        logger.warning(
            "PRE-CHECK FAIL — Reflective question detected: '%s'", initial_q_text[:80]
        )
        if db_session and question_id:
            pre_log = ValidationLog(
                id=str(uuid.uuid4()),
                question_id=question_id,
                attempt_number=0,
                layer="pre_check",
                score_or_verdict="fail (reflective_pattern)",
                feedback=(
                    "Soal bersifat reflektif/meta-learning (menanyakan tujuan pembelajaran "
                    "atau apa yang dipelajari). Harus diganti soal konten materi."
                ),
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(pre_log)
            db_session.commit()
        current_question = await _regenerate(
            ollama_client,
            generator_model,
            current_question,
            context_str,
            (
                "Soal ini bersifat reflektif — menanyakan tujuan pembelajaran atau apa yang dipelajari. "
                "Ganti dengan soal yang menanyakan FAKTA/NAMA/GERAKAN/ATURAN konkret dari materi buku. "
                "Gunakan bahasa sederhana yang mudah dipahami siswa SD usia 6-12 tahun."
            ),
        )
    # --- End Pre-check ---

    for attempt in range(1, max_attempts + 1):
        attempt_start = time.time()
        logger.info("-"*40)
        logger.info("Refinement attempt %d/%d", attempt, max_attempts)
        
        # --- Layer 1: Grounding Score ---
        logger.info("  [Layer 1] Computing grounding score...")
        options_raw = current_question.get("options")
        if isinstance(options_raw, dict):
            options_list = list(options_raw.values())
        elif isinstance(options_raw, list):
            options_list = options_raw
        else:
            options_list = []

        g_score = compute_grounding_score(
            current_question.get("question", ""),
            options_list,
            current_question.get("answer", ""),
            source_chunks,
            embedding_model,
        )

        is_grounded = validate_grounding(g_score, grounding_threshold)
        grounding_feedback = (
            "Grounded." if is_grounded else "Grounding score terlalu rendah. Soal harus lebih dekat ke materi sumber."
        )

        if db_session and question_id:
            log = ValidationLog(
                id=str(uuid.uuid4()),
                question_id=question_id,
                attempt_number=attempt,
                layer="grounding",
                score_or_verdict=f"{'pass' if is_grounded else 'fail'} (score={g_score:.3f})",
                feedback=grounding_feedback,
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(log)
            db_session.commit()

        if not is_grounded and attempt < max_attempts:
            logger.info("  Attempt %d: Grounding FAILED (score=%.3f < %.3f), regenerating...",
                        attempt, g_score, grounding_threshold)
            regen_start = time.time()
            current_question = await _regenerate(
                ollama_client, generator_model, current_question, context_str, grounding_feedback
            )
            logger.info("  Regeneration complete in %.2fs", time.time() - regen_start)
            logger.info("  Attempt %d completed in %.2fs", attempt, time.time() - attempt_start)
            continue

        # --- Auto-pass jika grounding sangat tinggi (skip LLM Judge) ---
        if g_score >= auto_pass_threshold and is_grounded:
            current_question["status"] = "final"
            current_question["refinement_count"] = attempt - 1
            total_elapsed = time.time() - loop_start
            logger.info(
                "  Attempt %d: Grounding AUTO-PASS (score=%.3f >= %.3f). Skipping Judge.",
                attempt, g_score, auto_pass_threshold
            )
            if db_session and question_id:
                auto_log = ValidationLog(
                    id=str(uuid.uuid4()),
                    question_id=question_id,
                    attempt_number=attempt,
                    layer="judge",
                    score_or_verdict=f"auto-pass (grounding={g_score:.3f})",
                    feedback="Auto-passed: grounding score melebihi threshold tinggi, Judge dilewati.",
                    created_at=datetime.now(timezone.utc),
                )
                db_session.add(auto_log)
                db_session.commit()
            logger.info("Refinement loop AUTO-PASS in %.2fs", total_elapsed)
            logger.info("="*50)
            return current_question

        # --- Layer 2: LLM Judge ---
        logger.info("  [Layer 2] Running LLM Judge evaluation...")
        await asyncio.sleep(LLM_CALL_THROTTLE_SEC)  # throttle sebelum call Judge
        judge_res = await evaluate_question(ollama_client, judge_model, current_question, context_str)

        if db_session and question_id:
            log = ValidationLog(
                id=str(uuid.uuid4()),
                question_id=question_id,
                attempt_number=attempt,
                layer="judge",
                score_or_verdict=f"{judge_res['verdict']} (score={judge_res.get('score', 0):.2f})",
                feedback=judge_res.get("feedback", ""),
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(log)
            db_session.commit()

        if judge_res["verdict"] == "pass":
            current_question["status"] = "final"
            current_question["refinement_count"] = attempt - 1
            total_elapsed = time.time() - loop_start
            logger.info("  Attempt %d: Judge PASSED (score=%.2f)", attempt, judge_res.get('score', 0))
            logger.info("Refinement loop PASSED at attempt %d (total time: %.2fs, status=final)",
                        attempt, total_elapsed)
            logger.info("="*50)
            return current_question

        if attempt < max_attempts:
            logger.info("  Attempt %d: Judge FAILED (score=%.2f), regenerating...",
                        attempt, judge_res.get('score', 0))
            regen_start = time.time()
            await asyncio.sleep(LLM_CALL_THROTTLE_SEC)  # throttle sebelum call Regen
            current_question = await _regenerate(
                ollama_client, generator_model, current_question, context_str, judge_res.get("feedback", "")
            )
            logger.info("  Regeneration complete in %.2fs", time.time() - regen_start)
        
        logger.info("  Attempt %d completed in %.2fs", attempt, time.time() - attempt_start)

    current_question["status"] = "needs_review"
    current_question["refinement_count"] = max_attempts
    total_elapsed = time.time() - loop_start
    logger.warning("Refinement loop exhausted all %d attempts (total time: %.2fs, status=needs_review)",
                   max_attempts, total_elapsed)
    logger.info("="*50)
    return current_question


async def _regenerate(
    ollama_client,
    generator_model: str,
    question: dict,
    context: str,
    feedback: str,
) -> dict:
    """Regenerate a question using feedback from validation."""
    logger.info("  Regenerating question with feedback (model=%s)", generator_model)
    logger.debug("    Feedback: %s", feedback[:150])
    
    regen_prompt = (
        f"Konteks:\n{context}\n\n"
        f"Soal sebelumnya:\n{json.dumps(question, ensure_ascii=False)}\n\n"
        f"Kritik: {feedback}\n"
        f"Perbaiki soal tersebut. Keluarkan hanya JSON array."
    )
    
    start_time = time.time()
    resp = await ollama_client.chat(
        model=generator_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": regen_prompt},
        ],
    )
    elapsed = time.time() - start_time
    
    try:
        text = resp["message"]["content"]
        logger.info("  Regeneration LLM response in %.2fs (%d chars)", elapsed, len(text))
        questions = parse_questions_response(text)
        if questions:
            parsed = questions[0]
            logger.info("  Regenerated question parsed successfully")
            return parsed
        else:
            logger.warning("  No valid question parsed from regeneration response, keeping previous version")
            return question
    except Exception as e:
        logger.warning("Failed to parse regenerated question (%s), keeping previous version", e)
        return question
