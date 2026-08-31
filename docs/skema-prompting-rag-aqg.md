# Skema Prompting Multi-Stage — RAG-AQG v4.0 (Isian/Esai, C1–C4, SD)

Dokumen ini merangkum seluruh alur orkestrasi prompting (alur umum end-to-end dan alur *multi-stage generation*) beserta seluruh *template prompt* final: 4 tahap generasi, LLM-as-Judge 5 aspek, dan *self-refinement loop*.

---

## A. Alur 1 — Alur Umum Sistem (End-to-End)

```text
[1] INGESTI & SECTION-AWARE CHUNKING
    PDF buku pelajaran diunggah
      -> Ekstraksi teks berbasis nomor halaman fisik (PageContent)
      -> Normalisasi karakter ligatur CID Kemdikbud & font doubling
      -> Penyaringan otomatis halaman Front-Matter & Back-Matter
      -> Section-Aware Chunking (200-450 kata berbasis heading & batas paragraf)
      -> Structural Content Tagging (materi_pokok, uraian, studi_kasus, rangkuman)
      -> Simpan chunk & metadata (page_number, chunk_index, section_type) ke SQLite
      -> Embedding chunk (BAAI/bge-m3) -> disimpan ke ChromaDB (dengan filter document_id)
      -> Tokenisasi Sparse BM25 dengan filter stopword Bahasa Indonesia
        |
        v
[2] PERMINTAAN DARI CHATBOT
    User: "Tolong buatkan 5 soal C4 bab 2"
      -> Ekstraksi parameter: jumlah_soal, target_bloom_level, bab/materi
      -> Sistem membatasi target_bloom_level HANYA C1-C4 untuk konteks jenjang SD
        |
        v
[3] HIGH-PRECISION HYBRID RETRIEVAL & RERANKING
    Query Transformation & Chapter Topic Expansion ("Bab 2" -> "Bab 2: Sistem Pernapasan Manusia")
      -> Candidate Pool Search (Top-15): Filtered Dense Search + BM25 (Weighted RRF)
      -> Refined Anti-Exercise Filter (eliminasi lembar soal bawaan buku)
      -> Cross-Score Semantic Reranker (70% Semantic Similarity + 30% RRF Score) -> Ambil Top-5 Chunk
      -> Parent Context Window Expansion (perluas chunk dengan teks sekitar hingga 2500 karakter)
        |
        v
[4] MULTI-STAGE LLM GENERATION (Lihat Alur 2 untuk detail)
    Context Window -> 4 tahap prompting -> draf soal (dengan stimulus kontekstual) + jawaban komunikatif + penjelasan + rubrik
      -> Deduplication (cek kemiripan soal pada sesi yang sama)
        |
        v
[5] 2-LAYER GUARDRAIL VALIDATION & SELF-REFINEMENT
    Pre-Check Anti-Reflektif (tolak pertanyaan meta-kognitif/tujuan belajar)
      -> Layer 1: Fast-Reject Grounding Check (Cosine Sim bge-m3 thd grounding_evidence)
           * Skor < 0.40 -> Fast-Reject (langsung ke Refinement Router)
           * Skor >= 0.40 -> Lolos Fast-Reject (wajib lanjut ke Layer 2 LLM Judge)
      -> Layer 2: LLM-as-Judge 5 Aspek SD (Llama-3.3-70B, T=0.05)
           * Grounding Faktual (Bebas Halusinasi)
           * Bloom Adherence (Wajib verifikasi keberadaan skenario stimulus nyata untuk C3/C4)
           * Bahasa Indonesia Ramah Anak SD (6-12 tahun)
           * Answerability (Keterjawaban Buku)
           * Answer Alignment (Ketepatan Kunci Jawaban)
      -> Keputusan Validasi:
           * PASS -> Soal berstatus 'final', disimpan ke DB & disajikan ke Chatbot.
           * FAIL & Attempt < 3 -> Refinement Router:
               - Masalah Redaksi / Stimulus / Jawaban -> Refinement Prompt A (Stage 4)
               - Masalah Target Bloom / Blueprint -> Refinement Prompt B (Stage 2-3)
               - Ulangi validasi Layer 1 & Layer 2.
           * FAIL & Attempt >= 3 -> Soal berstatus 'needs_review' (ditandai untuk tinjauan manual).
```

---

## B. Alur 2 — Alur Multi-Stage Prompting (Detail Tahap [4])

```text
Retrieved Context Window (Top-5 Chunks + Parent Context)
      |
      v
STAGE 1 -- Context Analysis Prompt (1x per request)
      | -> content_analysis (JSON: topik, konsep inti, fakta penting, testable_content)
      v
STAGE 2 -- Cognitive Bloom Planning Prompt (1x per request)
      | -> cognitive_plan (JSON: target Bloom C1-C4, KKO, stimulus_idea untuk anak SD)
      v
STAGE 3 -- Question Blueprint Prompt (per butir soal)
      | -> question_blueprint (JSON: knowledge_point, stimulus_context, grounding_evidence persis)
      v
STAGE 4 -- Question Packaging Prompt (per butir soal)
      | -> question [stimulus + pertanyaan] + expected_answer [komunikatif] + explanation [edukatif] + rubric (JSON)
      v
Diteruskan ke [5] Layer 1 Fast-Reject & Layer 2 LLM-as-Judge (Alur 1)
```

---

## C. Template Prompt — 4 Tahap Generasi

### Stage 1 — Context Analysis Prompt

```text
Anda adalah instructional content analyst untuk materi pelajaran Sekolah Dasar (SD).

Tugas Anda menganalisis materi pembelajaran berdasarkan CONTEXT yang diberikan.
Gunakan HANYA informasi yang terdapat dalam CONTEXT. Jangan menggunakan
pengetahuan eksternal apa pun.

Identifikasi:
1. topik utama
2. subtopik
3. konsep-konsep penting
4. fakta-fakta penting (harus berupa kalimat/klausa yang benar-benar ada di CONTEXT)
5. hubungan sebab-akibat atau perbandingan antar konsep (jika ada)
6. proses/tahapan (jika ada)
7. bagian teks yang paling berpotensi dijadikan dasar soal evaluasi
   (testable_content), sertakan kutipan kalimat sumbernya secara persis

CONTEXT:
{retrieved_context}

OUTPUT JSON:
{
  "topic": "...",
  "subtopics": [],
  "key_concepts": [],
  "key_facts": [],
  "relationships": [],
  "processes": [],
  "testable_content": [
    {"point": "...", "source_quote": "..."}
  ]
}
```

### Stage 2 — Cognitive Bloom Planning Prompt

```text
Anda adalah instructional designer yang menggunakan Revised Bloom's Taxonomy,
khusus untuk audiens siswa Sekolah Dasar (SD, usia 6-12 tahun).

TARGET COGNITIVE LEVEL: {target_bloom_level}
Cakupan level yang diizinkan HANYA: C1-Mengingat, C2-Memahami, C3-Menerapkan,
C4-Menganalisis. Level C5-Mengevaluasi dan C6-Mencipta TIDAK BOLEH digunakan
untuk jenjang SD.

CONTENT ANALYSIS:
{content_analysis}

Panduan operasi kognitif per level untuk jenjang SD:
- C1 (Mengingat): menyebutkan, menuliskan kembali, atau mengidentifikasi fakta/istilah eksplisit.
  -> Format: isian_singkat
- C2 (Memahami): menjelaskan makna, fungsi, atau prinsip sains dengan bahasa sendiri yang mudah dipahami.
  -> Format: isian_singkat atau esai
- C3 (Menerapkan): menggunakan konsep sains untuk memecahkan situasi konkret dalam kehidupan sehari-hari anak SD (contoh: kegiatan bermain, makan, merawat tanaman, cuaca).
  -> WAJIB rancang "stimulus_idea" berupa cerita/kasus singkat nyata.
  -> Format: esai
- C4 (Menganalisis): menelaah hubungan sebab-akibat, membandingkan dua kondisi/gejala, atau menyimpulkan dampak suatu peristiwa sains berdasarkan data/skenario konkret.
  -> WAJIB rancang "stimulus_idea" berupa skenario peristiwa/eksperimen sederhana.
  -> Format: esai

Tentukan:
1. cognitive_operation
2. student_task
3. stimulus_idea (ide skenario konkret kontekstual nyata anak SD, terutama untuk C3 dan C4)
4. reasoning_required
5. expected_evidence
6. recommended_question_format (isian_singkat / esai)
7. prohibited_question_pattern (pola pertanyaan yang harus dihindari agar level tidak meleset)

OUTPUT JSON:
{
  "cognitive_level": "...",
  "cognitive_operation": "...",
  "student_task": "...",
  "stimulus_idea": "...",
  "reasoning_required": "...",
  "expected_evidence": "...",
  "recommended_question_format": "...",
  "prohibited_question_pattern": []
}
```

### Stage 3 — Question Blueprint Prompt

```text
Anda adalah question designer untuk soal evaluasi SD berbentuk isian/esai.

Gunakan informasi berikut:

CONTENT ANALYSIS:
{content_analysis}

COGNITIVE PLAN:
{cognitive_plan}

Buat rancangan (blueprint) pertanyaan sebelum menulis pertanyaan final.

Tentukan:
1. knowledge_point (konsep/fakta spesifik yang diuji)
2. question_type (isian_singkat / esai)
3. stimulus_context (skenario cerita/studi kasus konkret anak SD jika target C3/C4, atau kosongkan jika C1/C2 murni)
4. question_intent (tujuan pengukuran kemampuan siswa)
5. grounding_evidence (WAJIB kutipan kalimat persis dari CONTEXT, bukan parafrase)
6. expected_answer_elements (poin-poin kunci yang wajib ada dalam jawaban ideal)
7. answer_scope (batasan kedalaman jawaban sesuai usia SD)
8. scoring_criteria (kriteria kasar penskoran)

Ketentuan:
1. Pertanyaan harus dapat dijawab sepenuhnya dari CONTEXT.
2. Untuk C3-C4, stimulus_context harus jelas dan memuat informasi situasi yang relevan.
3. grounding_evidence harus dapat ditelusuri kata per kata di CONTEXT.

OUTPUT JSON:
{
  "knowledge_point": "...",
  "question_type": "...",
  "stimulus_context": "...",
  "question_intent": "...",
  "grounding_evidence": "...",
  "expected_answer_elements": [],
  "answer_scope": "...",
  "scoring_criteria": []
}
```

### Stage 4 — Question Packaging Prompt

```text
Anda adalah generator soal evaluasi untuk siswa Sekolah Dasar (SD, usia 6-12 tahun).

Gunakan:

CONTEXT:
{retrieved_context}

QUESTION BLUEPRINT:
{question_blueprint}

Buat SATU paket soal lengkap yang terdiri dari [Pertanyaan], [Kunci Jawaban Ideal], [Penjelasan Materi], dan [Rubrik Skor], mengikuti QUESTION BLUEPRINT.

Ketentuan Khusus Jenjang SD:
1. Struktur Pertanyaan:
   - Jika target C3 atau C4: Awali pertanyaan dengan narasi/skenario stimulus konkret (1-3 kalimat ramah anak), lalu ajukan pertanyaan analitis/penerapannya.
   - Jika target C1 atau C2: Buat pertanyaan langsung yang lugas dan jelas.
2. Bahasa Indonesia: Gunakan kalimat komunikatif, kosakata akrab bagi anak SD (6-12 tahun), hindari kalimat ambigu atau berbelit-belit.
3. Kunci Jawaban (expected_answer): Rumuskan jawaban ideal yang faktual sesuai CONTEXT, namun disajikan dengan kalimat runtut, jelas, dan edukatif (jangan hanya menyalin potongan teks mentah).
4. Penjelasan (explanation): Berikan ulasan konsep materi yang mendidik mengapa jawaban tersebut benar.
5. Rubrik Penilaian (rubric): Susun kriteria penskoran bertingkat (skor 0, 1, 2) berdasarkan elemen kunci jawaban pada blueprint.
6. Jangan menyebutkan istilah "Bloom", "C1-C4", atau nomor bab di dalam teks pertanyaan.

OUTPUT JSON:
{
  "question": "...",
  "question_type": "...",
  "cognitive_level": "...",
  "knowledge_point": "...",
  "grounding_evidence": "...",
  "expected_answer": "...",
  "explanation": "...",
  "answer_elements": [
    {"element": "...", "weight": 1}
  ],
  "rubric": [
    {"score": 0, "criteria": "..."},
    {"score": 1, "criteria": "..."},
    {"score": 2, "criteria": "..."}
  ]
}
```

---

## D. Template Prompt — LLM-as-Judge (Layer 2) dan Refinement

### LLM-as-Judge Prompt (Evaluasi 5 Aspek SD)

```text
Anda adalah evaluator independen kualitas soal evaluasi untuk jenjang Sekolah Dasar (SD).

Evaluasi paket soal berikut secara holistik:
- Pertanyaan (question)
- Kunci Jawaban Ideal (expected_answer)
- Penjelasan Materi (explanation)
- Rubrik Skor (rubric)

CONTEXT RUJUKAN:
{retrieved_context}

GROUNDING EVIDENCE (klaim sistem):
{grounding_evidence}

PAKET SOAL:
Question: {question}
Expected Answer: {expected_answer}
Explanation: {explanation}
Rubric: {rubric}
Target Bloom: {target_bloom_level}

Evaluasi 5 Aspek Kualitas:
1. grounding — Apakah pertanyaan dan kunci jawaban 100% didukung oleh CONTEXT (bebas halusinasi)?
2. bloom_adherence — Level kognitif apa yang SEBENARNYA dituntut pertanyaan ini (evaluasi dari nol). Untuk level C3/C4, apakah soal memuat skenario stimulus konkret yang relevan?
3. bahasa — Apakah bahasa ramah anak usia SD (sederhana, komunikatif, tidak ambigu)?
4. answerability — Apakah pertanyaan dapat dijawab tuntas hanya menggunakan materi CONTEXT?
5. answer_alignment — Apakah expected_answer benar-benar menjawab inti pertanyaan yang diajukan?

OUTPUT JSON:
{
  "grounding": {"status": "pass/fail", "score": 1.0, "feedback": "..."},
  "bloom_adherence": {"status": "pass/fail", "detected_level": "...", "has_stimulus": true/false, "feedback": "..."},
  "bahasa": {"status": "pass/fail", "feedback": "..."},
  "answerability": {"status": "pass/fail", "feedback": "..."},
  "answer_alignment": {"status": "pass/fail", "feedback": "..."},
  "overall": "pass/fail",
  "failed_stage": "generation/planning/none"
}
```

### Refinement Router & Action Map

| failed_stage (dari Judge) | Aspek yang Gagal | Tindakan Sistem | Prompt yang Dipakai |
|---|---|---|---|
| `generation` | grounding, bahasa, answerability, answer_alignment | Re-entry ke Stage 4 (Direct Repair) | Refinement Prompt A |
| `planning` | bloom_adherence (mismatch Bloom / tanpa stimulus C3-C4) | Re-entry ke Stage 2 & Stage 3, lalu Stage 4 | Refinement Prompt B |

### Refinement Prompt A (Perbaikan di Level Generation)

```text
Anda adalah question refinement agent untuk soal evaluasi SD.

QUESTION SAAT INI: {question}
EXPECTED ANSWER SAAT INI: {expected_answer}
EXPLANATION SAAT INI: {explanation}
RUBRIC SAAT INI: {rubric}
QUESTION BLUEPRINT: {question_blueprint}
CONTEXT RUJUKAN: {retrieved_context}
FEEDBACK EVALUATOR: {validation_feedback}

Tugas: Perbaiki HANYA aspek yang dinyatakan gagal pada FEEDBACK EVALUATOR.
- Jika grounding gagal -> Sesuaikan klaim agar 100% sesuai grounding_evidence.
- Jika bahasa gagal -> Sederhanakan kosakata dan perjelas kalimat untuk anak SD.
- Jika stimulus kurang -> Tambahkan skenario situasi konkret sehari-hari anak SD.
- Jika answer_alignment gagal -> Selaraskan kunci jawaban dengan pertanyaan.

OUTPUT JSON: (Format sama persis dengan Stage 4)
{
  "question": "...",
  "question_type": "...",
  "cognitive_level": "...",
  "knowledge_point": "...",
  "grounding_evidence": "...",
  "expected_answer": "...",
  "explanation": "...",
  "answer_elements": [],
  "rubric": []
}
```

### Refinement Prompt B (Perbaikan di Level Planning / Bloom)

```text
Anda adalah instructional designer, bertugas merancang ulang rencana kognitif soal SD yang mengalami mismatch level Bloom.

COGNITIVE PLAN SEBELUMNYA: {cognitive_plan}
QUESTION YANG GAGAL: {question}
FEEDBACK EVALUATOR: {validation_feedback} (Detected: {detected_level}, Target: {target_bloom_level})
CONTENT ANALYSIS: {content_analysis}

Rancang ulang COGNITIVE PLAN agar tuntutan kognitifnya tepat sesuai TARGET BLOOM ({target_bloom_level}).
Jika target adalah C3 atau C4, wajib rancang stimulus_idea yang memuat skenario konkret kehidupan nyata anak SD.

OUTPUT JSON: (Format sama persis dengan Stage 2)
{
  "cognitive_level": "...",
  "cognitive_operation": "...",
  "student_task": "...",
  "stimulus_idea": "...",
  "reasoning_required": "...",
  "expected_evidence": "...",
  "recommended_question_format": "...",
  "prohibited_question_pattern": []
}
```
