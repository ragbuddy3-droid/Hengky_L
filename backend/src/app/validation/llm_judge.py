"""LLM-as-Judge validation (Layer 2)."""
import json
import re
import time
import logging
from app.generation.question_generator import extract_json_payload

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """Anda adalah evaluator soal (LLM-as-Judge) untuk soal esai dan isian singkat tingkat Sekolah Dasar (SD/MI) usia 6-12 tahun.

ATURAN KERAS — langsung beri verdict "fail" jika soal melanggar salah satu dari ini:

A. SOAL REFLEKTIF / META-LEARNING — fail jika soal mengandung pola seperti:
   "setelah mempelajari bab ini", "tujuan pembelajaran", "apa yang sudah kamu pelajari",
   "apa yang dapat kamu capai", "apa yang dapat kamu lakukan setelah",
   "apa yang perlu kamu lakukan untuk mengetahui", "apa manfaat mempelajari",
   "mengapa kita perlu belajar bab ini", "apa yang telah kamu pelajari".
   → Soal ini menguji proses belajar, bukan isi materi.

B. JAWABAN TERLALU ABSTRAK — fail jika jawaban adalah parafrase umum, bukan fakta konkret dari materi.
   Contoh jawaban BURUK: "Menyesuaikan keterampilan gerak", "Menerapkan strategi gerak",
   "Menjaga jarak yang pas" (tanpa penjelasan konkret).
   Jawaban BAIK menyebut nama, angka, cara, atau aturan yang spesifik dari teks materi.

C. BAHASA TERLALU SULIT UNTUK SD — fail jika soal menggunakan kata abstrak yang tidak dipahami
   anak usia 6-12 tahun: "memodifikasi", "mengaplikasikan strategi", "menganalisis",
   "apa yang penting", "apa yang dapat kamu capai".

RUBRIK PENILAIAN (jika tidak melanggar aturan keras A/B/C di atas):
1. Apakah soal menguji ISI MATERI (fakta/nama/gerakan/aturan), bukan proses belajar?
2. Apakah kunci jawaban KONKRET dan langsung didukung teks konteks materi?
3. Apakah tingkat taksonomi Bloom sesuai dengan kedalaman pertanyaan?
4. Apakah bahasa soal mudah dipahami siswa SD usia 6-12 tahun?

PENTING: Jangan tambahkan kata pengantar/penutup. Keluarkan respon dalam format JSON murni persis:
{
    "verdict": "pass",
    "score": 0.95,
    "feedback": "penjelasan spesifik dan saran perbaikan jika fail"
}"""


# Batasi panjang konteks yang dikirim ke Judge untuk menghemat token
JUDGE_CONTEXT_MAX_CHARS = 1500


async def evaluate_question(ollama_client, model_name: str, question: dict, source_context: str) -> dict:
    """Evaluate question using LLM as Judge."""
    q_text = question.get('question', '(unknown)')[:60]
    logger.info("LLM Judge evaluation starting (model=%s, question='%s...')", model_name, q_text)

    # Potong context agar tidak membuang token berlebih
    truncated_context = source_context[:JUDGE_CONTEXT_MAX_CHARS]
    if len(source_context) > JUDGE_CONTEXT_MAX_CHARS:
        truncated_context += "\n...[konteks dipotong]"
        logger.debug("Judge context truncated: %d → %d chars", len(source_context), len(truncated_context))

    prompt = (
        f"Konteks Materi (ringkas):\n{truncated_context}\n\n"
        f"Soal yang Dievaluasi:\n{json.dumps(question, indent=2, ensure_ascii=False)}\n\n"
        f"Lakukan evaluasi:"
    )
    
    start_time = time.time()
    response = await ollama_client.chat(
        model=model_name,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )
    elapsed = time.time() - start_time
    
    response_text = response['message']['content']
    logger.info("LLM Judge response received in %.2fs (%d chars)", elapsed, len(response_text))
    
    json_str = extract_json_payload(response_text)
        
    try:
        result = json.loads(json_str, strict=False)
    except Exception:
        try:
            from app.generation.question_generator import clean_json_string
            result = json.loads(clean_json_string(json_str), strict=False)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse judge response JSON: %s", e)
            logger.debug("  Response text (first 200 chars): %s", response_text[:200])
            return {
                "verdict": "fail",
                "score": 0.0,
                "feedback": "Failed to parse evaluation response"
            }

    verdict = result.get("verdict", "fail")
    score = float(result.get("score", 0.0))
    feedback = result.get("feedback", "No feedback provided")
    
    logger.info("LLM Judge result: verdict=%s, score=%.2f", verdict, score)
    logger.debug("  Feedback: %s", feedback[:150])
    
    return {
        "verdict": verdict,
        "score": score,
        "feedback": feedback
    }
