"""Prompt templates for Multi-Stage RAG-AQG pipeline (Optimized: Question, Answer, and Explanation).

Includes:
- System Persona constants (digunakan sebagai SystemMessage terpisah)
- Stage 1: Context Understanding Prompt
- Stage 2: Cognitive Bloom Planning Prompt
- Stage 3: Question Blueprint Prompt (single item, used by planning refinement)
- Stage 3 Batch: Question Blueprints for every question of one chunk
- Stage 4: Question Generation Prompt (Question + Answer + Explanation)
- LLM-as-Judge Prompt (Layer 2)
- Refinement Prompt A (Generation-level repair)
- Refinement Prompt B (Planning-level cognitive mismatch repair)
"""

# ── System Personas (digunakan sebagai SystemMessage terpisah) ──

SYSTEM_ANALYSIS_PERSONA = (
    "Anda adalah instructional content analyst untuk materi pelajaran Sekolah Dasar (SD). "
    "Aturan: (1) Gunakan HANYA informasi dari CONTEXT. (2) Respons HARUS format JSON valid tanpa markdown code block. "
    "(3) Jangan tambahkan pengetahuan di luar CONTEXT."
)

SYSTEM_DESIGNER_PERSONA = (
    "Anda adalah instructional designer menggunakan Revised Bloom's Taxonomy untuk siswa SD. "
    "Aturan: (1) Cakupan hanya C1-C4. (2) Respons HARUS format JSON valid tanpa markdown code block. "
    "(3) Jangan gunakan informasi di luar yang diberikan."
)

SYSTEM_GENERATOR_PERSONA = (
    "Anda adalah generator soal evaluasi untuk siswa Sekolah Dasar (SD). "
    "Aturan: (1) Gunakan Bahasa Indonesia sederhana dan ramah anak. (2) Respons HARUS format JSON valid tanpa markdown code block. "
    "(3) Soal, jawaban ideal, dan penjelasan harus sepenuhnya didukung CONTEXT."
)

SYSTEM_JUDGE_PERSONA = (
    "Anda adalah evaluator kualitas soal pendidikan untuk siswa Sekolah Dasar (SD). "
    "Aturan: (1) Evaluasi objektif dan independen. (2) Respons HARUS format JSON valid tanpa markdown code block."
)

SYSTEM_REFINEMENT_PERSONA = (
    "Anda adalah question refinement agent. "
    "Aturan: (1) Perbaiki HANYA aspek yang dinyatakan gagal pada feedback validator. (2) Jangan ubah yang sudah benar. "
    "(3) Respons HARUS format JSON valid tanpa markdown code block."
)


# ── Stage Prompts ──

STAGE1_CONTEXT_UNDERSTANDING_PROMPT = """Analisis materi pembelajaran berdasarkan CONTEXT yang diberikan.
Gunakan HANYA informasi yang terdapat dalam CONTEXT. Jangan menggunakan pengetahuan eksternal apa pun.

Identifikasi:
1. topik utama
2. subtopik
3. konsep-konsep penting
4. fakta-fakta penting (harus berupa kalimat/klausa yang benar-benar ada di CONTEXT)
5. hubungan sebab-akibat atau perbandingan antar konsep (jika ada)
6. proses/tahapan (jika ada)
7. bagian teks yang paling berpotensi dijadikan dasar soal evaluasi (testable_content), sertakan kutipan kalimat sumbernya secara persis

CONTEXT:
{retrieved_context}

OUTPUT JSON:
{{
  "topic": "...",
  "subtopics": ["..."],
  "key_concepts": ["..."],
  "key_facts": ["..."],
  "relationships": ["..."],
  "processes": ["..."],
  "testable_content": [
    {{"point": "...", "source_quote": "..."}}
  ]
}}
"""

STAGE2_COGNITIVE_PLANNING_PROMPT = """Rancang cognitive plan untuk soal evaluasi berdasarkan data berikut.

TARGET COGNITIVE LEVEL: {target_bloom_level}
Cakupan level yang diizinkan HANYA: C1-Mengingat, C2-Memahami, C3-Mengaplikasikan, C4-Menganalisis. Level C5-Mengevaluasi dan C6-Mencipta TIDAK BOLEH digunakan untuk jenjang SD.

Jika {target_bloom_level} berada di luar C1-C4, kembalikan status "invalid_level" dan hentikan proses tanpa melanjutkan ke bagian lain.

CONTENT ANALYSIS:
{content_analysis}

Panduan operasi kognitif per level untuk siswa SD (6-12 tahun):
- C1 (Mengingat): menyebutkan/mengidentifikasi fakta/nama/istilah eksplisit dari materi.
  -> cocok format: isian_singkat
- C2 (Memahami): menjelaskan konsep, proses, atau fungsi dengan kata-kata sendiri yang mudah dipahami anak SD.
  -> cocok format: isian_singkat atau esai_pendek
- C3 (Mengaplikasikan): menggunakan konsep sains pada situasi/peristiwa sehari-hari anak SD (memerlukan skenario/stimulus kontekstual nyata).
  -> cocok format: esai_pendek (harus memiliki skenario pendek)
- C4 (Menganalisis): menelaah sebab-akibat, membandingkan dua kondisi, atau memprediksi akibat suatu perubahan (memerlukan stimulus kasus sederhana).
  -> cocok format: esai (harus memiliki narasi kasus sebab-akibat)

Tentukan:
1. cognitive_operation (operasi berpikir target)
2. student_task (tugas spesifik siswa)
3. reasoning_required (alur penalaran yang diharapkan)
4. stimulus_idea (gagasan skenario/konteks sehari-hari untuk level C3/C4, atau kosong jika C1/C2)
5. expected_evidence (poin fakta buku yang menjadi dasar)
6. recommended_question_format (isian_singkat / esai_pendek / esai)
7. prohibited_question_pattern (pola yang dilarang agar level tidak meleset)

OUTPUT JSON:
{{
  "cognitive_level": "{target_bloom_level}",
  "cognitive_operation": "...",
  "student_task": "...",
  "reasoning_required": "...",
  "stimulus_idea": "...",
  "expected_evidence": "...",
  "recommended_question_format": "...",
  "prohibited_question_pattern": ["..."]
}}
"""

STAGE3_QUESTION_BLUEPRINT_PROMPT = """Buat rancangan (blueprint) pertanyaan evaluasi SD berbentuk isian/esai sebelum menulis pertanyaan final.

Gunakan informasi berikut:

CONTENT ANALYSIS:
{content_analysis}

COGNITIVE PLAN:
{cognitive_plan}

Tentukan:
1. knowledge_point (pokok materi spesifik yang diuji)
2. question_type (isian_singkat / esai_pendek / esai)
3. question_intent (indikator kompetensi yang diukur)
4. grounding_evidence (WAJIB kutipan kalimat persis dari CONTEXT/testable_content sebagai bukti materi)
5. stimulus_context (skenario/cerita singkat kehidupan nyata untuk C3/C4, atau string kosong jika C1/C2)
6. expected_answer_summary (ringkasan inti jawaban ideal yang diharapkan)
7. answer_scope (batasan panjang/kedalaman jawaban siswa SD)

Ketentuan:
1. Pertanyaan harus dapat dijawab sepenuhnya dari CONTEXT, tidak boleh membutuhkan pengetahuan di luar itu.
2. Untuk C3-C4, wajib sediakan stimulus_context konkret agar siswa tidak sekadar mengutip definisi. Skenario boleh fiktif, tetapi fakta yang dipakai dan penalaran yang diminta harus bisa diselesaikan dengan fakta di CONTEXT saja (jangan meminta mekanisme/akibat yang tidak dijelaskan CONTEXT).
3. grounding_evidence harus dapat ditelusuri kembali ke CONTEXT kata per kata.
4. question_type mengikuti recommended_question_format pada COGNITIVE PLAN.
5. Uji konsep/fakta materi, BUKAN pengalaman aktivitas kelas siswa.

OUTPUT JSON:
{{
  "knowledge_point": "...",
  "question_type": "...",
  "question_intent": "...",
  "grounding_evidence": "...",
  "stimulus_context": "...",
  "expected_answer_summary": "...",
  "answer_scope": "..."
}}
"""

STAGE3_BATCH_BLUEPRINT_PROMPT = """Buat rancangan (blueprint) untuk SETIAP butir soal evaluasi SD berbentuk isian/esai di bawah ini sebelum menulis pertanyaan final. Semua butir berasal dari CONTEXT yang sama.

CONTEXT:
{chunk_text}

COGNITIVE PLAN PER LEVEL:
{cognitive_plans}

DAFTAR BUTIR (poin materi, kutipan sumber, dan level target):
{items}

Untuk setiap butir tentukan:
1. knowledge_point (pokok materi spesifik yang diuji, sesuai poin butir)
2. question_type (isian_singkat / esai_pendek / esai, mengikuti recommended_question_format level butir)
3. question_intent (indikator kompetensi yang diukur)
4. grounding_evidence (WAJIB kutipan kalimat persis dari CONTEXT sebagai bukti materi)
5. stimulus_context (skenario/cerita singkat kehidupan nyata untuk C3/C4, atau string kosong jika C1/C2)
6. expected_answer_summary (ringkasan inti jawaban ideal yang diharapkan)
7. answer_scope (batasan panjang/kedalaman jawaban siswa SD)

Ketentuan:
1. Pertanyaan harus dapat dijawab sepenuhnya dari CONTEXT, tidak boleh membutuhkan pengetahuan di luar itu.
2. Untuk C3-C4, wajib sediakan stimulus_context konkret agar siswa tidak sekadar mengutip definisi. Skenario boleh fiktif, tetapi fakta yang dipakai dan penalaran yang diminta harus bisa diselesaikan dengan fakta di CONTEXT saja (jangan meminta mekanisme/akibat yang tidak dijelaskan CONTEXT).
3. grounding_evidence harus dapat ditelusuri kembali ke CONTEXT kata per kata.
4. Uji konsep/fakta materi, BUKAN pengalaman aktivitas kelas siswa.
5. Setiap butir harus menguji aspek yang BERBEDA. Jika dua butir memakai poin yang sama, pilih sudut yang berbeda (misal fungsi, proses, sebab-akibat, atau contoh) agar soalnya tidak kembar.
6. Kembalikan tepat satu blueprint per butir, urut sesuai nomor butir.

OUTPUT JSON:
{{
  "blueprints": [
    {{
      "item": 1,
      "knowledge_point": "...",
      "question_type": "...",
      "question_intent": "...",
      "grounding_evidence": "...",
      "stimulus_context": "...",
      "expected_answer_summary": "...",
      "answer_scope": "..."
    }}
  ]
}}
"""

STAGE4_QUESTION_GENERATION_PROMPT = """Buat SATU butir soal evaluasi {question_type} untuk siswa SD beserta jawaban ideal dan penjelasan edukatif, mengikuti QUESTION BLUEPRINT.

Gunakan:

CONTEXT:
{retrieved_context}

QUESTION BLUEPRINT:
{question_blueprint}

CONTOH SOAL SEJENIS (few-shot):
{few_shot_examples}

Ketentuan Khusus Penulisan Soal SD:
1. Kesesuaian Kognitif ({target_bloom_level}):
   - Untuk C1/C2: Buat pertanyaan langsung yang jelas dan mudah dipahami.
   - Untuk C3/C4: Sertakan narasi/stimulus situasi sehari-hari yang ramah anak sebelum mengajukan pertanyaan analitis.
2. Gaya Bahasa: Gunakan Bahasa Indonesia yang sederhana, komunikatif, bersahabat, kalimat pendek, dan tidak ambigu bagi siswa SD. Sapa siswa dengan "kamu", bukan "Anda".
3. Hindari Kata Larangan: Jangan sebut kata 'Bloom', 'C1-C4', 'Bab', atau 'Halaman' di dalam teks soal.
4. Faktual & Anti-Halusinasi: Semua fakta sains, mekanisme, organ, angka, atau konsep dalam `question`, `expected_answer`, dan `explanation` HARUS 100% bersumber dari CONTEXT dan `grounding_evidence`. DILARANG menambahkan fakta ilmiah atau konsep di luar materi yang diberikan, walaupun fakta itu benar menurut pengetahuan umum.
5. Aturan Khusus C3/C4 — Skenario Boleh Fiktif, Fakta Tidak:
   - Tokoh, tempat, dan kejadian dalam skenario boleh rekaan (misal "Bayangkan kamu berada di ...").
   - Tetapi setiap FAKTA yang dipakai di skenario, pertanyaan, jawaban, dan penjelasan (sifat benda, angka, sebab-akibat, mekanisme) harus tertulis di CONTEXT.
   - Penalaran siswa hanya boleh menggabungkan, membandingkan, atau menerapkan fakta CONTEXT. Jangan meminta siswa menjelaskan mekanisme atau akibat yang tidak dijelaskan CONTEXT (contoh salah: CONTEXT hanya memuat data periode revolusi, lalu soal meminta menjelaskan pengaruhnya pada musim).
   - Jika CONTEXT hanya berisi data/fakta tanpa penjelasan sebab-akibat, buat soal perbandingan atau penerapan data tersebut.
6. Jawaban Ideal (expected_answer): Harus 100% didukung fakta materi CONTEXT, dirumuskan dengan kalimat utuh, komunikatif, dan runtut sebagai standar kunci jawaban guru. Jangan menambah fakta pelengkap dari luar CONTEXT.
7. Penjelasan (explanation): Berikan penjelasan ringkas dan edukatif mengapa jawaban tersebut benar, hanya dengan merujuk fakta di CONTEXT.
8. Soal Mandiri & Jelas: Soal harus bisa dipahami oleh siswa yang membacanya tanpa mengikuti pelajaran di kelas. Sebut langsung nama konsep/objek/peristiwanya. DILARANG merujuk pengalaman kelas seperti "yang telah kamu pelajari", "yang sudah kalian lakukan", "di kelas", "di sekolahmu", atau "aktivitas tadi". DILARANG juga merujuk teks sumber seperti "dalam teks", "menurut bacaan", atau "yang disebutkan dalam materi", karena siswa tidak melihat CONTEXT.
11. Harus Bisa Dijawab: Tanyakan hanya informasi yang benar-benar tertulis di CONTEXT. Jika CONTEXT tidak menyebut suatu detail (nama, angka, tempat), jangan tanyakan detail itu. `expected_answer` tidak boleh berbunyi "tidak disebutkan" atau sejenisnya.
9. Satu Pertanyaan: Tulis tepat SATU pertanyaan per butir. Jangan menambahkan pertanyaan kedua (contoh salah: "Jelaskan cara bermainnya. Apa tujuannya?").
10. Akhiri pertanyaan dengan tanda tanya (?), atau dengan titik (.) jika berupa kalimat perintah seperti "Jelaskan ..." / "Sebutkan ...".

OUTPUT JSON:
{{
  "question": "...",
  "question_type": "{question_type}",
  "cognitive_level": "{target_bloom_level}",
  "knowledge_point": "...",
  "grounding_evidence": "...",
  "expected_answer": "...",
  "explanation": "..."
}}
"""

LLM_JUDGE_PROMPT = """Evaluasi paket soal evaluasi SD berikut secara objektif dan teliti — question, expected_answer, dan explanation dinilai sebagai satu kesatuan.

CONTEXT:
{retrieved_context}

GROUNDING EVIDENCE:
{grounding_evidence}

QUESTION:
{question}

EXPECTED ANSWER:
{expected_answer}

EXPLANATION:
{explanation}

TARGET BLOOM:
{target_bloom_level}

Evaluasi 5 aspek kualitas:
1. grounding — periksa SETIAP klaim fakta (sifat benda, angka, sebab-akibat, mekanisme, contoh) di question, expected_answer, DAN explanation satu per satu terhadap CONTEXT.
   - Tokoh/tempat/kejadian rekaan dalam skenario C3/C4 boleh, asalkan fakta yang dipakai ada di CONTEXT.
   - "fail" jika ada SATU saja klaim fakta yang tidak tertulis di CONTEXT, walaupun benar menurut pengetahuan umum, atau jika jawaban menarik kesimpulan sebab-akibat yang tidak dinyatakan CONTEXT.
   - Pada feedback, sebutkan klaim yang tidak didukung CONTEXT secara persis.
2. bloom_adherence — evaluasi level kognitif yang SEBENARNYA dituntut soal ini (deteksi ulang secara independen). Apakah cocok dengan TARGET BLOOM? (Catatan: C3/C4 untuk SD membutuhkan skenario/analisis sebab-akibat, bukan hafalan definisi).
3. bahasa — apakah bahasa jelas, komunikatif, ramah anak usia SD (6-12 tahun), berisi SATU pertanyaan, dan mandiri (tidak merujuk "yang telah kamu pelajari/lakukan di kelas" maupun "dalam teks/bacaan", karena siswa tidak melihat teks sumbernya)?
4. answerability — apakah soal dapat dijawab tuntas hanya dengan membaca CONTEXT yang ada? "fail" jika siswa membutuhkan pengetahuan di luar CONTEXT untuk menjawab, jika soal menanyakan detail yang tidak tertulis di CONTEXT, atau jika expected_answer menyatakan informasinya "tidak disebutkan"/"tidak dijelaskan".
5. answer_alignment — apakah expected_answer & explanation menjawab question secara tepat, runtut, konsisten (tidak saling bertentangan), dan edukatif?

"overall" adalah "pass" HANYA jika kelima aspek "pass"; satu aspek "fail" berarti "overall" = "fail".

Tentukan "failed_stage":
- "generation" jika masalah ada pada fakta di luar CONTEXT, redaksi bahasa, format jawaban, atau kejelasan teks
- "planning" jika level kognitif tidak sesuai target (misal C4 tetapi soalnya hanya hafalan C1)
- "none" jika seluruh aspek lolos (pass)

OUTPUT JSON:
{{
  "grounding": {{"status": "pass", "score": 1.0, "feedback": "Fakta didukung konteks materi."}},
  "bloom_adherence": {{"status": "pass", "detected_level": "...", "feedback": "Sesuai target kognitif."}},
  "bahasa": {{"status": "pass", "feedback": "Bahasa ramah anak SD dan mudah dipahami."}},
  "answerability": {{"status": "pass", "feedback": "Dapat dijawab dari konteks."}},
  "answer_alignment": {{"status": "pass", "feedback": "Jawaban tepat dan relevan dengan pertanyaan."}},
  "overall": "pass",
  "failed_stage": "none"
}}
"""

REFINEMENT_PROMPT_A = """Perbaiki HANYA aspek yang dinyatakan gagal pada FEEDBACK VALIDATOR. Jangan mengubah knowledge_point atau cognitive_operation yang sudah benar.

QUESTION SAAT INI:
{question}

EXPECTED ANSWER SAAT INI:
{expected_answer}

EXPLANATION SAAT INI:
{explanation}

QUESTION BLUEPRINT (acuan asli, jangan diubah):
{question_blueprint}

CONTEXT:
{retrieved_context}

FEEDBACK VALIDATOR:
{validation_feedback}

Ketentuan:
1. Jika grounding/answerability gagal -> hapus atau ganti setiap klaim fakta yang tidak tertulis di CONTEXT (di question, expected_answer, dan explanation), gunakan ulang grounding_evidence dari blueprint. Untuk C3/C4 skenario boleh tetap fiktif, tetapi pertanyaannya harus bisa dijawab hanya dengan fakta CONTEXT; jika perlu ubah pertanyaan menjadi perbandingan/penerapan fakta CONTEXT.
2. Jika bahasa/ambiguity gagal -> sederhanakan kalimat, hilangkan makna ganda.
3. Jika answer_alignment gagal -> sesuaikan expected_answer dan explanation agar konsisten dengan question.
4. Jangan menambahkan informasi dari luar CONTEXT.
5. Pertahankan question_type dan cognitive_level yang sama.
6. Soal harus mandiri dan berisi SATU pertanyaan; jangan merujuk pengalaman kelas ("yang telah kamu pelajari/lakukan", "di kelas", "di sekolahmu").

OUTPUT JSON:
{{
  "question": "...",
  "question_type": "{question_type}",
  "cognitive_level": "{target_bloom_level}",
  "knowledge_point": "...",
  "grounding_evidence": "...",
  "expected_answer": "...",
  "explanation": "..."
}}
"""

REFINEMENT_PROMPT_B = """Rancang ulang COGNITIVE PLAN agar operasi kognitifnya benar-benar sesuai TARGET BLOOM ({target_bloom_level}), bukan {detected_level}. Perhatikan pola pertanyaan sebelumnya yang menyebabkan level meleset, dan masukkan ke prohibited_question_pattern agar tidak terulang.

COGNITIVE PLAN SEBELUMNYA:
{cognitive_plan}

QUESTION YANG GAGAL:
{question}

FEEDBACK VALIDATOR:
{validation_feedback}
(detected_level: {detected_level}, target: {target_bloom_level})

CONTENT ANALYSIS:
{content_analysis}

OUTPUT JSON:
{{
  "cognitive_level": "{target_bloom_level}",
  "cognitive_operation": "...",
  "student_task": "...",
  "reasoning_required": "...",
  "expected_evidence": "...",
  "recommended_question_format": "...",
  "prohibited_question_pattern": ["..."]
}}
"""
