"""Question generation with Ollama / Groq LLM."""
import json
import re
import time
import logging

logger = logging.getLogger(__name__)

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
   Contoh DUPLIKAT yang harus dihindari:
   - "Apa yang harus dilakukan untuk mengoper bola?" DAN "Apa yang penting saat mengoper bola?"

4. JANGAN membuat soal pilihan ganda. HANYA "esai" atau "isian_singkat".

5. Kunci jawaban harus KONKRET dan langsung dari teks materi, bukan parafrase abstrak.
   - Contoh BURUK : "Menyesuaikan keterampilan gerak"
   - Contoh BAIK  : "Posisi kaki selebar bahu, lutut sedikit ditekuk, bola dipegang setinggi dada"

49. JANGAN sertakan pemikiran, penalaran, atau tag <think>. LANGSUNG dan HANYA keluarkan format array JSON murni persis seperti berikut:
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
Catatan: Nilai "question_type" harus berupa "esai" atau "isian_singkat".
"""

def strip_reasoning_tags(text: str) -> str:
    """Remove <think>...</think> or <thought>...</thought> blocks and unclosed tags."""
    if not text:
        return ""
    # Strip complete thinking blocks
    cleaned = re.sub(r'<(think|thought)>[\s\S]*?</\1>', '', text, flags=re.IGNORECASE)
    # Strip unclosed thinking block if present
    cleaned = re.sub(r'<(think|thought)>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_json_string(s: str) -> str:
    """Clean common LLM JSON formatting errors such as trailing commas."""
    if not s:
        return ""
    # Remove trailing commas before closing brackets/braces: ,] -> ] and ,} -> }
    s = re.sub(r',\s*([\]}])', r'\1', s)
    return s.strip()


def extract_fallback_objects(text: str) -> list[dict]:
    """Fallback: extract individual JSON objects containing 'question' key."""
    results = []
    # Match JSON objects {...} that contain "question"
    pattern = r'\{[^{}]*?"question"\s*:\s*[\s\S]*?\}'
    matches = re.finditer(pattern, text)
    for m in matches:
        obj_str = m.group(0)
        try:
            obj = json.loads(clean_json_string(obj_str), strict=False)
            if isinstance(obj, dict) and "question" in obj:
                results.append(obj)
        except Exception:
            pass
    return results


def extract_json_payload(response_text: str) -> str:
    """Extract JSON payload from markdown backticks, array [...], or object {...} with reasoning tag stripping."""
    if not response_text:
        return ""

    # 1. Strip reasoning/thinking tags first
    cleaned_text = strip_reasoning_tags(response_text)
    text_to_search = cleaned_text if cleaned_text else response_text

    # 2. Try extracting from markdown code blocks ```json ... ``` or ``` ... ```
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text_to_search, re.IGNORECASE)
    for block in code_blocks:
        b_strip = block.strip()
        if (b_strip.startswith('[') and b_strip.endswith(']')) or (b_strip.startswith('{') and b_strip.endswith('}')):
            return b_strip
        if b_strip:
            try:
                json.loads(clean_json_string(b_strip), strict=False)
                return b_strip
            except Exception:
                pass

    # 3. Search for outermost JSON array [...]
    first_bracket = text_to_search.find('[')
    last_bracket = text_to_search.rfind(']')
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = text_to_search[first_bracket:last_bracket+1].strip()
        try:
            json.loads(clean_json_string(candidate), strict=False)
            return candidate
        except Exception:
            pass

    # 4. Search for outermost JSON object {...}
    first_brace = text_to_search.find('{')
    last_brace = text_to_search.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text_to_search[first_brace:last_brace+1].strip()
        try:
            json.loads(clean_json_string(candidate), strict=False)
            return candidate
        except Exception:
            pass

    # 5. Fallback: try code blocks or bracket bounds on raw response_text if cleaned_text differed
    if cleaned_text and text_to_search != response_text:
        orig_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text, re.IGNORECASE)
        for block in orig_blocks:
            b_strip = block.strip()
            if '<think>' not in b_strip.lower() and '<thought>' not in b_strip.lower():
                try:
                    json.loads(clean_json_string(b_strip), strict=False)
                    return b_strip
                except Exception:
                    pass

        f_b = response_text.find('[')
        l_b = response_text.rfind(']')
        if f_b != -1 and l_b != -1 and l_b > f_b:
            return response_text[f_b:l_b+1].strip()

    return text_to_search.strip()


def build_prompt(context_chunks: list[str], num_questions: int, chapter: str | None, bloom_level: str | None, chat_history: str | None) -> str:
    logger.info("Building prompt: num_questions=%d, chapter=%s, bloom_level=%s, context_chunks=%d",
                num_questions, chapter or '(all)', bloom_level or '(all)', len(context_chunks))
    
    context_str = "\n\n".join(context_chunks)
    prompt = f"Konteks materi:\n{context_str}\n\n"
    
    if chat_history:
        prompt += f"Konteks percakapan:\n{chat_history}\n\n"
        logger.debug("  Chat history context included (%d chars)", len(chat_history))
        
    prompt += (
        f"Buatlah TEPAT {num_questions} soal yang MASING-MASING MENANYAKAN ASPEK BERBEDA "
        f"tentang ISI MATERI dari konteks buku di atas untuk siswa SD (usia 6-12 tahun). "
        f"ATURAN PENTING: "
        f"(1) setiap soal HARUS menanyakan fakta/nama/gerakan/aturan yang BERBEDA satu sama lain, "
        f"(2) JANGAN buat dua soal yang mirip atau menanyakan hal yang sama, "
        f"(3) JANGAN soal tentang tujuan pembelajaran, refleksi, atau apa yang dipelajari, "
        f"(4) gunakan bahasa yang mudah dipahami anak SD."
    )

    if chapter:
        prompt += f" Fokus pada bab/topik: {chapter}."

    if bloom_level:
        prompt += f" Gunakan tingkat kognitif Bloom: {bloom_level}."
    
    logger.debug("  Final prompt length: %d chars", len(prompt))
    return prompt


def parse_questions_response(response_text: str) -> list[dict]:
    """Parse LLM JSON output into structured questions with robust error handling."""
    if not response_text:
        logger.warning("Empty response_text provided to parse_questions_response")
        return []

    logger.info("Parsing LLM response (%d chars)", len(response_text))
    
    json_str = extract_json_payload(response_text)
    
    # Attempt 1: Standard json.loads
    try:
        result = json.loads(json_str, strict=False)
        if isinstance(result, list):
            logger.info("Successfully parsed %d questions from response", len(result))
            return result
        elif isinstance(result, dict):
            logger.info("Successfully parsed single question dict from response")
            return [result]
    except Exception as e:
        logger.debug("Attempt 1 json.loads failed: %s", e)

    # Attempt 2: Clean trailing commas & retry
    cleaned_json = clean_json_string(json_str)
    try:
        result = json.loads(cleaned_json, strict=False)
        if isinstance(result, list):
            logger.info("Successfully parsed %d questions after comma cleanup", len(result))
            return result
        elif isinstance(result, dict):
            return [result]
    except Exception as e:
        logger.debug("Attempt 2 comma cleanup failed: %s", e)

    # Attempt 3: Fallback object extraction via regex
    fallback_objs = extract_fallback_objects(response_text)
    if fallback_objs:
        logger.info("Successfully recovered %d questions using fallback regex object extraction", len(fallback_objs))
        return fallback_objs

    logger.error("Failed to parse questions JSON. Raw snippet: %s", response_text[:300])
    return []

async def generate_questions(ollama_client, model_name: str, context_chunks: list[str], num_questions: int = 5, **kwargs) -> list[dict]:
    """Call LLM API, parse response, return list of question dicts."""
    chapter = kwargs.get('chapter')
    bloom_level = kwargs.get('bloom_level')
    chat_history = kwargs.get('chat_history')
    
    logger.info("="*50)
    logger.info("Starting question generation (model=%s, num_questions=%d)", model_name, num_questions)
    
    prompt = build_prompt(context_chunks, num_questions, chapter, bloom_level, chat_history)
    
    logger.info("Calling LLM API (model=%s)...", model_name)
    start_time = time.time()
    
    response = await ollama_client.chat(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )
    
    elapsed = time.time() - start_time
    response_text = response['message']['content']
    logger.info("LLM response received in %.2fs (%d chars)", elapsed, len(response_text))
    
    questions = parse_questions_response(response_text)
    logger.info("Question generation complete: %d questions produced", len(questions))
    logger.info("="*50)
    return questions
