# Skema Prompting Multi-Stage — RAG-AQG (Isian/Esai, C1–C4, SD)

Dokumen ini merangkum dua alur (alur umum sistem end-to-end, dan alur multi-stage prompting di dalamnya) beserta seluruh template prompt final: 4 tahap generasi, LLM-as-Judge, dan refinement.

---

## A. Alur 1 — Alur Umum Sistem (End-to-End)

```
[1] INGESTI DOKUMEN
    PDF diunggah
      -> Ekstraksi teks + pembersihan (header/footer/nomor halaman)
      -> fix chunk / semantic chunking
      -> Metadata & teks chunk disimpan di SQLite
      -> Embedding chunk -> disimpan sebagai vektor di ChromaDB
        |
        v
[2] PERMINTAAN DARI CHAT
    User: "Tolong buatkan 5 soal C4 bab 2"
      -> Ekstraksi parameter: jumlah_soal, target_bloom_level, bab/materi
      -> (Sistem membatasi target_bloom_level hanya C1-C4 untuk konteks SD)
        |
        v
[3] HYBRID RETRIEVAL
    BM25 (keyword) + ChromaDB (semantic) -> Reciprocal Rank Fusion
      -> Filter: hanya chunk berkategori Konsep / Narasi / Instruksi
      -> Buang chunk berkategori Evaluasi (soal bawaan buku, agar tidak dijiplak)
        |
        v
[4] LLM GENERATION  <-- lihat Alur 2 (Multi-Stage Prompting) untuk detail
    Context relevan -> 4 tahap prompting -> draf soal + kunci jawaban + rubrik
      -> Deduplication (cek kemiripan dengan soal lain di sesi yang sama)
        |
        v
[5] VALIDASI & SELF-REFINEMENT (2 Layer)
    Pre-Check (tolak pola soal reflektif/tujuan belajar)
      -> Layer 1: Grounding Check (cosine similarity thd grounding_evidence, non-LLM)
      -> Layer 2: LLM-as-Judge (bahasa, kesesuaian Bloom, answerability, dll.)
      -> Valid?
           YA    -> Soal Final ditampilkan ke user
           TIDAK -> Refinement Prompt (re-entry ke tahap yang relevan, lihat bagian D)
                    -> ulangi Layer 1 & 2
                    -> maksimal N percobaan, lalu tandai "perlu ditinjau manual" jika tetap gagal
```

Catatan: Layer 1 (Grounding Check) sebaiknya dihitung terhadap `grounding_evidence` spesifik dari blueprint (Alur 2, Tahap 3), bukan terhadap seluruh isi chunk — supaya deteksi halusinasi lebih presisi, terutama pada chunk yang panjang.

---

## B. Alur 2 — Alur Multi-Stage Prompting (Detail Tahap [4])

```
Retrieved Context (per chunk)
      |
      v
STAGE 1 -- Context Understanding Prompt
      | -> content_analysis (JSON)
      v
STAGE 2 -- Cognitive Bloom Planning Prompt
      | -> cognitive_plan (JSON)
      v
STAGE 3 -- Question Blueprint Prompt
      | -> question_blueprint (JSON, termasuk grounding_evidence)
      v
STAGE 4 -- Question Generation Prompt
      | -> question + expected_answer + rubric (JSON, satu paket)
      v
   diteruskan ke [5] Layer 1 & Layer 2 (Alur 1)
```

---

## C. Template Prompt — 4 Tahap Generasi

### Stage 1 — Context Understanding Prompt

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
khusus untuk audiens siswa Sekolah Dasar (SD).

TARGET COGNITIVE LEVEL: {target_bloom_level}
Cakupan level yang diizinkan HANYA: C1-Mengingat, C2-Memahami, C3-Menerapkan,
C4-Menganalisis. Level C5-Mengevaluasi dan C6-Mencipta TIDAK BOLEH digunakan
untuk jenjang SD.

Jika {target_bloom_level} berada di luar C1-C4, kembalikan status "invalid_level"
dan hentikan proses tanpa melanjutkan ke bagian lain.

CONTENT ANALYSIS:
{content_analysis}

Panduan operasi kognitif per level (gunakan sebagai referensi, jangan disalin mentah):
- C1 (Mengingat): menyebutkan/mengidentifikasi fakta eksplisit
  -> cocok question_format: isian_singkat
- C2 (Memahami): menjelaskan makna/istilah dengan kalimat sendiri
  -> cocok question_format: isian_singkat atau esai_pendek
- C3 (Menerapkan): menggunakan konsep/langkah pada situasi baru yang sejenis
  -> cocok question_format: esai_pendek
- C4 (Menganalisis): menjelaskan hubungan, perbandingan, atau sebab-akibat
  -> cocok question_format: esai

Tentukan:
1. cognitive_operation
2. student_task
3. reasoning_required
4. expected_evidence
5. recommended_question_format (isian_singkat / esai_pendek / esai)
6. prohibited_question_pattern (pola pertanyaan yang harus dihindari agar level
   tidak turun/naik, contoh: untuk C4 hindari pola "Apa yang dimaksud dengan...")

Ketentuan:
1. Jangan membuat pertanyaan final di tahap ini.
2. Jangan menggunakan informasi di luar CONTENT ANALYSIS.
3. cognitive_operation harus konsisten dengan target_bloom_level.

OUTPUT JSON:
{
  "cognitive_level": "...",
  "cognitive_operation": "...",
  "student_task": "...",
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
1. knowledge_point (spesifik, bukan topik umum)
2. question_type (pilih sesuai recommended_question_format:
   isian_singkat / esai_pendek / esai)
3. question_intent (apa yang ingin diukur dari siswa)
4. grounding_evidence (WAJIB kutipan kalimat persis dari CONTEXT/testable_content,
   bukan parafrase)
5. expected_answer_elements (poin-poin kunci yang wajib ada dalam jawaban ideal)
6. answer_scope (batasan panjang/kedalaman jawaban, sesuaikan usia SD)
7. scoring_criteria (kriteria kasar untuk menilai jawaban, disempurnakan di Stage 4)

Ketentuan:
1. Pertanyaan harus dapat dijawab sepenuhnya dari CONTEXT, tidak boleh
   membutuhkan pengetahuan di luar itu.
2. question_type dan struktur soal harus konsisten dengan cognitive_operation
   pada COGNITIVE PLAN.
3. Untuk target C3-C4, expected_answer_elements TIDAK BOLEH bisa dijawab hanya
   dengan mengutip satu kalimat definisi.
4. grounding_evidence harus dapat ditelusuri kembali ke CONTEXT kata per kata.

OUTPUT JSON:
{
  "knowledge_point": "...",
  "question_type": "...",
  "question_intent": "...",
  "grounding_evidence": "...",
  "expected_answer_elements": [],
  "answer_scope": "...",
  "scoring_criteria": []
}
```

### Stage 4 — Question Generation Prompt (soal + jawaban + rubrik jadi satu paket)

```text
Anda adalah generator soal evaluasi untuk siswa Sekolah Dasar (SD).

Gunakan:

CONTEXT:
{retrieved_context}

QUESTION BLUEPRINT:
{question_blueprint}

CONTOH SOAL SEJENIS (few-shot, level & tipe soal yang sama):
{few_shot_examples}

Buat SATU pertanyaan {question_type} beserta jawaban ideal dan rubrik
penilaiannya, mengikuti QUESTION BLUEPRINT.

Ketentuan:
1. Pertanyaan harus sepenuhnya didukung oleh grounding_evidence pada blueprint;
   jangan menambahkan fakta di luar CONTEXT.
2. Pertanyaan harus mencerminkan cognitive_operation target
   ({target_bloom_level}), bukan sekadar hafalan jika levelnya C3-C4.
3. Gunakan Bahasa Indonesia yang sederhana, kalimat pendek, hindari istilah
   abstrak tanpa penjelasan, sesuai usia siswa SD.
4. Hindari kalimat bermakna ganda atau pertanyaan dengan banyak interpretasi.
5. Jangan menyebutkan kata "Bloom", nama level kognitif, atau nomor bab di
   dalam teks pertanyaan.
6. expected_answer harus 100% bersumber dari CONTEXT.
7. rubric harus punya minimal 3 tingkat skor, disusun berdasarkan
   expected_answer_elements pada blueprint.

OUTPUT JSON:
{
  "question": "...",
  "question_type": "...",
  "cognitive_level": "...",
  "knowledge_point": "...",
  "grounding_evidence": "...",
  "expected_answer": "...",
  "answer_elements": [
    {"element": "...", "weight": 0}
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

### LLM-as-Judge Prompt

```text
Anda adalah evaluator kualitas soal pendidikan untuk siswa Sekolah Dasar (SD).

Evaluasi paket soal berikut secara bersamaan — question, expected_answer, dan
rubric adalah satu kesatuan yang harus dinilai bersama, bukan terpisah.

CONTEXT:
{retrieved_context}

GROUNDING EVIDENCE (klaim dari sistem):
{grounding_evidence}

QUESTION:
{question}

EXPECTED ANSWER:
{expected_answer}

RUBRIC:
{rubric}

TARGET BLOOM:
{target_bloom_level}

Evaluasi aspek berikut:
1. grounding — apakah question & expected_answer benar-benar didukung CONTEXT
   (bukan halusinasi)?
2. bloom_adherence — level kognitif apa yang SEBENARNYA dituntut pertanyaan ini
   (deteksi ulang dari nol, jangan percaya label sistem), apakah cocok dengan
   TARGET BLOOM?
3. bahasa — apakah bahasa sesuai usia SD (sederhana, tidak ambigu)?
4. answerability — apakah pertanyaan dapat dijawab hanya dari CONTEXT?
5. answer_alignment — apakah expected_answer benar-benar menjawab question?
6. rubric_alignment — apakah rubric konsisten dengan expected_answer?

Ketentuan:
1. detected_level HARUS ditentukan secara independen, jangan hanya menyalin
   TARGET BLOOM.
2. Jika salah satu aspek gagal, cantumkan feedback spesifik dan actionable
   (bukan generik seperti "perlu diperbaiki").
3. Tentukan juga "failed_stage" untuk membantu proses perbaikan:
   - "generation" jika masalah hanya di redaksi/bahasa/grounding pada teks akhir
   - "planning" jika masalah di level kognitif yang tidak sesuai target

OUTPUT JSON:
{
  "grounding": {"status": "pass/fail", "score": 0.0, "feedback": "..."},
  "bloom_adherence": {"status": "pass/fail", "detected_level": "...", "feedback": "..."},
  "bahasa": {"status": "pass/fail", "feedback": "..."},
  "answerability": {"status": "pass/fail", "feedback": "..."},
  "answer_alignment": {"status": "pass/fail", "feedback": "..."},
  "rubric_alignment": {"status": "pass/fail", "feedback": "..."},
  "overall": "pass/fail",
  "failed_stage": "generation/planning/none"
}
```

### Refinement Router (logika non-LLM di layer orkestrasi)

Router ini membaca `failed_stage` dan aspek yang gagal dari output judge untuk memutuskan prompt refinement mana yang dipakai dan tahap mana yang di-re-entry, alih-alih selalu mengulang dari Stage 1.

| failed_stage (dari judge) | Aspek yang gagal | Re-entry ke | Prompt yang dipakai |
|---|---|---|---|
| generation | grounding, bahasa, answerability, answer_alignment, rubric_alignment | Stage 4 saja | Refinement Prompt A |
| planning | bloom_adherence | Stage 2 & 3 diulang, lalu Stage 4 lagi | Refinement Prompt B |

### Refinement Prompt A (perbaikan di level generation)

```text
Anda adalah question refinement agent.

QUESTION SAAT INI:
{question}

EXPECTED ANSWER SAAT INI:
{expected_answer}

RUBRIC SAAT INI:
{rubric}

QUESTION BLUEPRINT (acuan asli, jangan diubah):
{question_blueprint}

CONTEXT:
{retrieved_context}

FEEDBACK VALIDATOR:
{validation_feedback}

Perbaiki HANYA aspek yang dinyatakan gagal pada FEEDBACK VALIDATOR. Jangan
mengubah knowledge_point atau cognitive_operation yang sudah benar.

Ketentuan:
1. Jika grounding gagal -> ganti bagian yang tidak didukung CONTEXT, gunakan
   ulang grounding_evidence dari blueprint.
2. Jika bahasa/ambiguity gagal -> sederhanakan kalimat, hilangkan makna ganda.
3. Jika answer_alignment/rubric_alignment gagal -> sesuaikan expected_answer
   dan rubric agar konsisten dengan question.
4. Jangan menambahkan informasi dari luar CONTEXT.
5. Pertahankan question_type dan cognitive_level yang sama.

OUTPUT JSON: (format sama persis dengan Stage 4)
{
  "question": "...",
  "question_type": "...",
  "cognitive_level": "...",
  "knowledge_point": "...",
  "grounding_evidence": "...",
  "expected_answer": "...",
  "answer_elements": [],
  "rubric": []
}
```

### Refinement Prompt B (perbaikan di level planning, mismatch Bloom)

```text
Anda adalah instructional designer, bertugas merancang ulang rencana kognitif
soal yang gagal validasi.

COGNITIVE PLAN SEBELUMNYA:
{cognitive_plan}

QUESTION YANG GAGAL:
{question}

FEEDBACK VALIDATOR:
{validation_feedback}
(detected_level: {detected_level}, target: {target_bloom_level})

CONTENT ANALYSIS:
{content_analysis}

Rancang ulang COGNITIVE PLAN agar operasi kognitifnya benar-benar sesuai
TARGET BLOOM ({target_bloom_level}), bukan {detected_level}. Perhatikan pola
pertanyaan sebelumnya yang menyebabkan level meleset, dan masukkan ke
prohibited_question_pattern agar tidak terulang.

OUTPUT JSON: (format sama persis dengan Stage 2)
{
  "cognitive_level": "...",
  "cognitive_operation": "...",
  "student_task": "...",
  "reasoning_required": "...",
  "expected_evidence": "...",
  "recommended_question_format": "...",
  "prohibited_question_pattern": []
}
```

Setelah Refinement Prompt B menghasilkan cognitive_plan baru, jalankan ulang
Stage 3 (Question Blueprint) dengan cognitive_plan tersebut, lalu Stage 4, lalu
validasi ulang di Layer 1 & Layer 2 — hingga lolos atau mencapai batas
maksimal percobaan.

---

## E. Ringkasan Perbedaan Kunci dari TwinStar

1. TwinStar tidak berbasis RAG per-chunk, sehingga urutan round-nya level
   dulu baru topik. Sistem ini sudah punya topik terkunci dari retrieval,
   sehingga Context Understanding wajar berjalan lebih dulu.
2. TwinStar untuk pilihan ganda tidak perlu kunci jawaban/rubrik eksplisit.
   Untuk isian/esai, expected_answer + rubric wajib digenerate dan divalidasi
   sebagai satu paket dengan question.
3. TwinStar mengulang generation dari awal saat validasi gagal. Skema ini
   menambahkan refinement router yang re-entry ke tahap paling relevan
   (Stage 4 saja untuk masalah redaksi/grounding, Stage 2-3 untuk masalah
   level kognitif), sehingga lebih efisien dan bisa menjadi poin kebaruan
   metode di skripsi.
