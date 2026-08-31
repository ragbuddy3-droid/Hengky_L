# PRD — RAG-AQG: Sistem Automatic Question Generation Berbasis RAG (v4.0)

## 0. Informasi Dokumen

1. **Nama Produk**: RAG-AQG (Retrieval-Augmented Generation for Automatic Question Generation)
2. **Pemilik Proyek**: Hengky Laurencio
3. **Versi**: 4.0
4. **Dokumen Terkait**: `ARCHITECTURE.md`, `DIAGRAM_SKEMA_SISTEM.md`, `SKEMA_BACKEND_LENGKAP.md`, `skema-prompting-rag-aqg.md`

---

## 1. Ringkasan Produk

**RAG-AQG v4.0** adalah aplikasi web modern berbasis *Retrieval-Augmented Generation* (RAG) yang mengotomatisasi pembuatan soal evaluasi esai dan isian singkat berkualitas tinggi untuk jenjang Sekolah Dasar (SD, usia 6–12 tahun) dari dokumen buku pelajaran digital (PDF).

Sistem mematuhi kaidah Taksonomi Bloom (fokus pada level C1–C4) dengan mengintegrasikan **Section-Aware Chunking**, **High-Precision Hybrid Retrieval dengan Semantic Reranking**, **Multi-Stage Pedagogical Prompting (dengan skenario stimulus situasional untuk level aplikasi & analisis)**, serta **Validasi 2-Layer (Fast-Reject Grounding + LLM-as-Judge 5 Aspek)** guna menjamin soal yang dihasilkan 100% faktual (*grounded*), bebas halusinasi, dan ramah anak.

---

## 2. Masalah yang Dipecahkan

1. **Efisiensi Pendidik**: Menyusun soal evaluasi berbasis stimulus kontekstual yang valid dan terstruktur secara manual membutuhkan waktu dan tenaga yang besar bagi guru.
2. **Risiko Halusinasi AI**: LLM murni sering berhalusinasi, menciptakan fakta semu, atau memberikan kunci jawaban yang tidak terdapat di buku sumber.
3. **Penyimpangan Level Kognitif**: Soal level C3 (Menerapkan) dan C4 (Menganalisis) sering kali turun kelas menjadi soal C1/C2 hafalan jika tidak dilengkapi skenario stimulus situasional konkret yang sesuai dengan dunia anak SD.
4. **Fragmentasi Konteks Buku**: Metode *fixed chunking* tradisional memotong kalimat di tengah jalan dan membuang relasi bab/nomor halaman, sehingga sistem RAG kehilangan konteks utuh.

---

## 3. Target Pengguna

1. **Guru / Pendidik Sekolah Dasar**: Pengguna utama yang mengunggah buku materi (IPAS, PJOK, PKN, Matematika), meminta pembuatan soal per bab melalui chatbot interaktif, dan menerima paket soal yang sudah tervalidasi lengkap dengan kunci jawaban, rubrik, dan penjelasan.
2. **Peneliti & Pengembang (Skripsi)**: Memantau dan menganalisis kualitas generasi melalui *Multi-Stage Trace Inspector*, log evaluasi juri 5 aspek, metrik keberhasilan validasi, dan waktu latensi eksekusi.

---

## 4. Tujuan & Metrik Keberhasilan

| Tujuan Kualitas | Target Metrik | Metode Pengukuran |
|---|---|---|
| **1. Groundedness & Anti-Halusinasi** | Faktual Grounding $\ge 95\%$ | Cosine Similarity Lapis 1 ($\ge 0.40$) + Evaluasi Aspek Grounding LLM-as-Judge Lapis 2. |
| **2. Bloom Adherence (C1–C4 SD)** | Kesesuaian Kognitif $\ge 90\%$ | LLM Judge memverifikasi kesesuaian target level Bloom dan keberadaan skenario stimulus nyata pada soal C3/C4. |
| **3. Kelayakan Bahasa Anak SD** | Kesesuaian Bahasa $\ge 95\%$ | Evaluasi keterbacaan, kesederhanaan kosakata, dan kejelasan kalimat untuk rentang usia 6–12 tahun. |
| **4. Presisi Retrieval Materi** | Precision@5 $\ge 85\%$ | Candidate Pool (Top-15) disaring via Cross-Score Semantic Reranker ke Top-5 chunk terbaik. |
| **5. Kehandalan Sistem Validasi** | Defect Pass Rate $= 0\%$ | Eliminasi celah false auto-pass; semua soal wajib diaudit oleh LLM Judge sebelum berstatus `final`. |

---

## 5. Ruang Lingkup Fitur (v4.0)

### 5.1 Manajemen Dokumen & Section-Aware Ingestion
1. Upload file PDF buku pelajaran dengan validasi ukuran dan format MIME.
2. Ekstraksi teks berbasis halaman fisik asli (`PageContent`) dan pembersihan otomatis halaman *front-matter* (cover, kata pengantar, daftar isi) serta *back-matter* (glosarium, indeks, profil penulis).
3. Normalisasi karakter ligatur CID Kemdikbud (`(cid:1652)` $\rightarrow$ `fi`) dan perbaikan anomali font ganda.
4. **Section-Aware Chunking**: Memotong materi berdasarkan batas heading bab/sub-bab dan batas paragraf utuh (target 200–450 kata) dengan overlap 2 kalimat.
5. **Structural Content Tagging**: Menandai tipe materi (`materi_pokok`, `uraian_materi`, `studi_kasus`, `aktivitas_diskusi`, `rangkuman`) dengan regex bab ketat.
6. Drawer Visualisasi Chunk: Menampilkan nomor halaman fisik, indeks chunk, jenis struktural, dan konten teks tiap chunk.

### 5.2 High-Precision Retrieval & Expansion
1. **Query Transformation & Chapter Topic Expansion**: Memperluas query pendek (contoh: *"Bab 2"*) menjadi nama topik bab riil di database (*"Bab 2: Sistem Pernapasan Manusia"*).
2. **Document-ID Filtered Dense Search**: Pencarian vektor ChromaDB dibatasi hanya pada dokumen yang sedang aktif.
3. **Lexical Search (BM25)**: Tokenizer BM25 dilengkapi penghapusan stopword Bahasa Indonesia.
4. **Weighted Reciprocal Rank Fusion (RRF)**: Menggabungkan Dense & Sparse ranking ($0.6 \text{ Dense} + 0.4 \text{ Sparse}$).
5. **Refined Anti-Exercise Filter**: Menyaring lembar latihan soal buku agar model tidak menjiplak tugas buku.
6. **Cross-Score Semantic Reranker**: Menghitung skor gabungan semantik ($70\% \text{ Cosine Sim} + 30\% \text{ RRF Score}$) untuk memilih Top-5 chunk paling relevan dari 15 kandidat.
7. **Parent Context Window Expansion**: Memperluas chunk terpilih dengan materi sekitar hingga 2500 karakter sebelum disuplai ke prompt generator.

### 5.3 Multi-Stage Pedagogical Prompting
1. **Stage 1 (Context Analysis)**: Ekstraksi topik, konsep inti, fakta penting, dan konten yang dapat diuji (*testable content*).
2. **Stage 2 (Cognitive Bloom Planning)**: Penetapan operasi kognitif C1–C4 dan perancangan ide stimulus (`stimulus_idea`) khusus anak SD.
3. **Stage 3 (Question Blueprinting)**: Perancangan cetak biru butir soal, skenario stimulus kontekstual (`stimulus_context`), dan kutipan bukti (*grounding evidence*).
4. **Stage 4 (Question Packaging)**: Pembuatan butir soal utuh yang memadukan [Stimulus Konkret] + [Pertanyaan Analitis/Isian] + [Kunci Jawaban Ideal Komunikatif] + [Penjelasan Materi Ramah Anak] + [Rubrik Penskoran Bertingkat].

### 5.4 2-Layer Guardrails & Self-Refinement Loop
1. **Lapis 1: Fast-Reject Grounding Filter**: Menghitung kemiripan kosinus embedding teks soal+jawaban terhadap `grounding_evidence` spesifik ($< 0.40 \rightarrow$ penolakan cepat ke perbaikan).
2. **Lapis 2: LLM-as-Judge 5 Aspek**: Evaluasi mendalam oleh model $70\text{B}$ ($T=0.05$) untuk 5 rubrik:
   - *Grounding Faktual*
   - *Bloom Adherence* (termasuk verifikasi stimulus nyata C3/C4)
   - *Bahasa Indonesia Ramah Anak SD*
   - *Answerability* (keterjawaban buku)
   - *Answer Alignment* (keselarasan kunci jawaban)
3. **Smart Refinement Router**: 
   - Kegagalan generasi $\rightarrow$ **Refinement Prompt A** (perbaikan teks di Stage 4).
   - Kegagalan kognitif $\rightarrow$ **Refinement Prompt B** (perancangan ulang di Stage 2–3).
   - Maksimal 3 iterasi perbaikan.

### 5.5 Bank Soal & Multi-Stage Inspector
1. Tampilan daftar bank soal lengkap dengan filter status kelolosan validasi.
2. **Tab Paket Soal & Rubrik**: Melihat teks stimulus, pertanyaan, kunci jawaban, penjelasan, dan rubrik skor.
3. **Tab 4 Tahap Generasi**: Menginspeksi artefak JSON dari Stage 1 s.d. Stage 4.
4. **Tab Validasi 2-Layer**: Melihat riwayat evaluasi Lapis 1 & 2 serta rincian breakdown 5 aspek juri.
5. **Tab Raw Prompt Traces**: Transparansi penuh teks prompt yang dikirim ke LLM, latensi ms, dan output mentah.
6. **Tab Konteks Buku (Used Chunks)**: Menampilkan kutipan materi rujukan lengkap dengan referensi nomor halaman buku asli (`Hal. X`).

---

## 6. Arsitektur Teknologi

- **Backend API**: Python 3.11+, FastAPI, `uv`, SQLAlchemy ORM, Pydantic v2.
- **Workflow & RAG**: LangGraph StateGraph (`AQGState`), LangChain, ChromaDB, `rank_bm25`, `BAAI/bge-m3`.
- **Model Inference**: DeepInfra OpenAI-compatible API (`Qwen/Qwen3-32B` untuk generator, `meta-llama/Llama-3.3-70B-Instruct-Turbo` untuk judge).
- **Database**: SQLite (WAL Mode).
- **Frontend App**: Next.js 15 (App Router, TypeScript), Mantine UI v7 (`@mantine/core`, `@mantine/dropzone`), Tabler Icons, `bun`.
