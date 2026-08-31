# Diagram Skema Sistem Menyeluruh (RAG-AQG v4.0)

Dokumen ini berisi kumpulan diagram visual berbasis **Mermaid** yang menjelaskan seluruh skema arsitektur, alur data (*data flow*), orkestrasi *state graph*, dan hubungan basis data sistem **RAG-AQG (Retrieval-Augmented Generation for Automatic Question Generation)** versi 4.0.

---

## 1. Diagram Arsitektur Global & Alur End-to-End

Diagram ini memvisualisasikan bagaimana setiap komponen (Frontend, FastAPI Router, Ingestion, Storage, LangGraph Engine, dan LLM/Embedding Models) saling terhubung secara modular.

```mermaid
flowchart TB
    subgraph ClientLayer ["1. Frontend Web Layer (Next.js 15 + Mantine UI v7)"]
        UI_Upload["Halaman Manajemen Dokumen PDF\n(Dropzone & Chunk Drawer)"]
        UI_Chat["Antarmuka AQG Chatbot Stream\n(Intent Parser & Suggestion Chips)"]
        UI_Audit["Halaman Bank & Trace Inspector\n(4 Stages, 2-Layer Logs, Used Chunks)"]
    end

    subgraph APILayer ["2. Backend API Layer (FastAPI v1)"]
        EP_Doc["/api/v1/documents\n(Upload, Page Extraction, Chunks)"]
        EP_Chat["/api/v1/chat\n(Sessions, Messages, Background Trigger)"]
        EP_Quest["/api/v1/questions\n(List, Detail, Prompt Traces, Logs)"]
    end

    subgraph IngestionEngine ["3. Ingestion & Preprocessing Pipeline"]
        PDF_Extract["PDF Page-Aware Extractor\n(PageContent Dataclass)"]
        Font_Norm["CID Ligature & Font Cleaner\n((cid:1652) -> fi, KKaattaa -> Kata)"]
        FBM_Filter["Front & Back Matter Filter\n(Prakata, Daftar Isi, Glosarium, Indeks)"]
        Section_C["SectionAwareChunker (Default)\n(200-450 kata, Heading & Paragraph Split)"]
        Struct_Tag["Structural Content Classifier\n(materi_pokok, uraian, studi_kasus, rangkuman)"]
    end

    subgraph StorageLayer ["4. Persistence & Index Layer"]
        DB_Relational[("SQLite Database (WAL Mode)\n- documents\n- chunks (page_no, chunk_idx, sec_type)\n- chat_sessions\n- chat_messages\n- questions\n- validation_logs")]
        Vector_DB[("ChromaDB Vector Store\n(BAAI/bge-m3 Embeddings + DocID Filter)")]
        BM25_Index["BM25 Lexical Sparse Index\n(Indonesian Stopwords Tokenizer)"]
    end

    subgraph GraphEngine ["5. LangGraph AQG StateGraph Engine"]
        N1["Node 1: retrieve_context\n(Query Expansion + Hybrid Search + Reranker)"]
        N2["Node 2: generate_questions\n(Stages 1-4 + Bloom C1-C4 SD Stimulus + Parent Window)"]
        N3["Node 3: grounding_validation\n(Layer 1: Fast-Reject Cosine Sim < 0.40)"]
        N4["Node 4: llm_judge_evaluation\n(Layer 2: LLM-as-Judge 5 Aspek SD)"]
        N5["Node 5: self_refinement\n(Smart Router: Refinement A / Refinement B)"]
        N6["Node 6: persist_questions\n(Save Soal, Traces, Used Chunks, & Warnings)"]
    end

    subgraph ModelLayer ["6. Model & Inference Layer"]
        LLM_Gen["LLM Generator (Qwen-32B / Gemma-4)\n(Stage 1-4 Multi-Stage Prompts)"]
        LLM_Judge["LLM Judge (Llama-3.3-70B, T=0.05)\n(5-Aspect Elementary Rubric)"]
        Emb_Model["Embedding Model (BAAI/bge-m3)\n(Cosine Grounding & Vector Search)"]
    end

    %% Client to API
    UI_Upload -->|POST File PDF| EP_Doc
    UI_Chat -->|POST Pesan / Request Soal| EP_Chat
    UI_Audit -->|GET Detail & Traces| EP_Quest

    %% API to Ingestion
    EP_Doc -->|Background Task| PDF_Extract
    PDF_Extract --> Font_Norm --> FBM_Filter --> Section_C --> Struct_Tag
    Struct_Tag -->|Simpan Chunk & Metadata| DB_Relational
    Struct_Tag -->|Index Dense Vector| Vector_DB
    Struct_Tag -->|Index Sparse BM25| BM25_Index

    %% Chat to LangGraph
    EP_Chat -->|Trigger Background AQG| GraphEngine
    EP_Quest -->|Read Soal & Logs| DB_Relational

    %% Graph Engine Internal Flow
    N1 -->|Top-5 Reranked Context Chunks| N2
    N2 -->|Candidate Questions (Package)| N3
    N3 -->|Fast-Reject (< 0.40)| N5
    N3 -->|Pass Fast-Reject (>= 0.40)| N4
    N4 -->|Judge Pass| N6
    N4 -->|Judge Fail & Attempt < 3| N5
    N4 -->|Judge Fail & Attempt >= 3| N6
    N5 -->|Re-Evaluate| N3
    N6 -->|Next Item| N3

    %% Graph to Storage & Models
    N1 <--> Vector_DB
    N1 <--> BM25_Index
    N1 <--> DB_Relational
    N2 <--> LLM_Gen
    N3 <--> Emb_Model
    N4 <--> LLM_Judge
    N5 <--> LLM_Gen
    N6 --> DB_Relational
```

---

## 2. Diagram Pipeline Ingestion & Preprocessing Teks

Diagram ini mendetailkan bagaimana buku digital PDF diekstrak, dinormalisasi dari artefak font Kemdikbud, disaring halamannya, dan dipotong secara Section-Aware.

```mermaid
flowchart TD
    Start([1. File PDF Diunggah]) --> ReadPDF["2. Page-Aware PDF Extraction\n(Ekstraksi per Halaman Fisik -> PageContent)"]
    
    ReadPDF --> CleanFont["3. CID Ligature & Font Doubling Normalization\n- (cid:1652) -> fi, (cid:1651) -> fl\n- KKaattaa -> Kata"]
    
    CleanFont --> FilterFront{"4. Cek Halaman Front-Matter?"}
    FilterFront -->|Ya: Cover, Kata Pengantar, Daftar Isi, Petunjuk| DropFM[Abaikan Halaman Front-Matter]
    FilterFront -->|Tidak| FilterBack{"5. Cek Halaman Back-Matter?"}
    
    FilterBack -->|Ya: Glosarium, Indeks, Profil Penulis/Penerbit| DropBM[Abaikan Halaman Back-Matter]
    FilterBack -->|Tidak| SectionChunker["6. SectionAwareChunker (Default Engine)"]
    
    SectionChunker --> SplitStrategy["• Deteksi Heading & Sub-heading Markdown\n• Potong berbasis Batas Paragraf (\\n\\n)\n• Target Ukuran: 200 - 450 kata (~1200 - 2200 char)\n• Overlap Kontekstual: 2 Kalimat Utuh"]
    
    SplitStrategy --> StructClassify["7. Structural Content Classification & Metadata Tagging"]
    
    StructClassify --> TagDetails["• Klasifikasi Tag: materi_pokok / uraian_materi / studi_kasus / aktivitas_diskusi / rangkuman\n• Regex Bab Ketat: ^(?:BAB|UNIT|TEMA|MODUL)\\s+([0-9IVXLCDM]+)\n• Metadata: page_number, chunk_index, section_type, chapter, heading"]
    
    TagDetails --> SaveDB[("8. Simpan Chunk ke SQLite (Tabel chunks)")]
    TagDetails --> EmbedChunk["9. Generate Vector Embedding (BAAI/bge-m3)"]
    EmbedChunk --> SaveVector[("10. Simpan Vector ke ChromaDB\n(Metadata: document_id, page_number, chunk_index)")]
    
    SaveDB --> Ready([Status Dokumen: READY])
    SaveVector --> Ready
```

---

## 3. Diagram High-Precision Retrieval & Cross-Score Reranking

Diagram ini menjelaskan alur pemrosesan query pengguna, ekspansi topik bab, pencarian hybrid ber-filter, hingga pemilihan Top-5 chunk terbaik via Semantic Reranker.

```mermaid
flowchart TD
    UserQuery["User Prompt\n(misal: 'Buatkan 5 soal C4 bab 2')"] --> QueryExpansion["1. Query Transformation & Chapter Topic Expansion\n(Ambil Judul Bab Riil di DB: 'Bab 2: Sistem Pernapasan Manusia')"]
    
    QueryExpansion --> SearchPool["2. Dual-Engine Candidate Retrieval"]
    
    subgraph DualRetrieval ["Candidate Search Pool (Top-15)"]
        SearchPool --> Dense["Dense Vector Search (ChromaDB bge-m3)\n- Filter Wajib: where={'document_id': doc_id}\n- Cosine Similarity Search"]
        SearchPool --> Sparse["Sparse Lexical Search (BM25)\n- Indonesian Stopwords Removal\n- Term Matching"]
    end
    
    Dense --> RRF["3. Weighted Reciprocal Rank Fusion (RRF)\nRRF_Score = 0.6/(60 + Rank_Dense) + 0.4/(60 + Rank_Sparse)"]
    Sparse --> RRF
    
    RRF --> AntiExercise{"4. Refined Anti-Exercise Filter"}
    AntiExercise -->|Lembar Soal Bawaan Buku Murni Tanpa Konsep| DropExercise[Eliminasi Chunk Latihan]
    AntiExercise -->|Lolos: Materi Pokok / Uraian / Studi Kasus| CandidatePool["Pool Kandidat Terpilih (15 Chunk)"]
    
    CandidatePool --> Reranker["5. Cross-Score Semantic Reranker\nFinal_Score = 0.70 * Cosine_Similarity + 0.30 * RRF_Score"]
    
    Reranker --> Top5["6. Ambil Top-5 Chunk Paling Relevan"]
    
    Top5 --> WindowExpansion["7. Parent Context Window Expansion\n(Gabungkan Chunk Terpilih + Konteks Pendukung Sekitar hingga 2500 char)"]
    
    WindowExpansion --> LLMPrompt([Suplai Konteks ke Multi-Stage Generator])
```

---

## 4. Diagram Alur StateGraph Multi-Stage AQG & Validasi 2-Layer

Diagram ini menjelaskan alur orkestrasi LangGraph dalam merancang pedagogi kognitif, membuat stimulus nyata untuk siswa SD, dan menjalankan validasi dual-layer.

```mermaid
stateDiagram-v2
    [*] --> retrieve_context : Inisialisasi State (AQGState)
    
    retrieve_context --> generate_questions : Top-5 Chunks & Parent Window Siap
    
    state generate_questions {
        [*] --> Stage1 : Level Materi (1x Run)
        Stage1 --> Stage2 : Level Target Bloom (1x Run)
        
        state "Stage 1: Context Analysis" as Stage1 {
            direction TB
            Extract["Ekstraksi Konsep Inti, Fakta Faktual, & Testable Content"]
        }
        
        state "Stage 2: Cognitive Bloom Planning" as Stage2 {
            direction TB
            Plan["Penetapan Operasi Kognitif C1-C4 & Perancangan Stimulus_Idea SD"]
        }
        
        Stage2 --> ItemGen : Level Butir Soal (Paralel Max 3 Concurrency)
        
        state "Stage 3 & 4: Blueprint & Generation" as ItemGen {
            Stage3["Stage 3: Question Blueprint\n(Poin Uji, Stimulus_Context, & Grounding Evidence)"] --> Stage4["Stage 4: Question Packaging\n(Skenario Konkret + Pertanyaan + Kunci Jawaban Edukatif + Penjelasan Ramah Anak)"]
        }
        
        ItemGen --> DedupFilter : Deduplikasi Soal & Poin Uji
        DedupFilter --> [*] : Hasil: Raw Candidate Question Packages
    }

    generate_questions --> grounding_validation : Validasi Butir Soal ke-i
    generate_questions --> [*] : Gagal (Konteks Kosong)

    state "Lapis 1: Fast-Reject Grounding Check" as grounding_validation {
        [*] --> CheckReflective : Pre-check Anti-Reflektif
        CheckReflective --> RejectReflective : Terdeteksi Soal Reflektif
        CheckReflective --> CalcCosine : Hitung Cosine Sim (bge-m3) vs Grounding Evidence
        
        CalcCosine --> FastReject : Score < 0.40 (Tolak Cepat ke Refinement)
        CalcCosine --> FastPass : Score >= 0.40 (Lolos ke LLM Judge)
    }

    grounding_validation --> self_refinement : Fast-Reject (< 0.40) & Attempt < 3
    grounding_validation --> persist_questions : Fast-Reject & Attempt >= 3 (status = needs_review)
    grounding_validation --> llm_judge_evaluation : Score >= 0.40 (Wajib Masuk Juri)

    state "Lapis 2: LLM-as-Judge Evaluation (5 Aspek SD)" as llm_judge_evaluation {
        [*] --> Eval5Aspects
        state Eval5Aspects {
            A1["1. Grounding Faktual (Bebas Halusinasi)"]
            A2["2. Bloom Adherence (Verifikasi Stimulus Nyata C3/C4)"]
            A3["3. Bahasa Indonesia Ramah Anak SD (6-12 Thn)"]
            A4["4. Answerability (Keterjawaban Materi)"]
            A5["5. Answer Alignment (Ketepatan Kunci Jawaban)"]
        }
        Eval5Aspects --> JudgePass : Overall == 'pass'
        Eval5Aspects --> JudgeFail : Overall == 'fail' (failed_stage: planning / generation)
    }

    llm_judge_evaluation --> persist_questions : Judge Pass (status = final)
    llm_judge_evaluation --> self_refinement : Judge Fail & Attempt < 3
    llm_judge_evaluation --> persist_questions : Judge Fail & Attempt >= 3 (status = needs_review)

    state "Node 5: Smart Self-Refinement Router" as self_refinement {
        [*] --> CheckFailedStage
        CheckFailedStage --> RefinementB : failed_stage == 'planning' (Redesign Bloom & Blueprint)
        CheckFailedStage --> RefinementA : failed_stage == 'generation' (Perbaiki Redaksi, Stimulus & Jawaban)
        RefinementB --> S3_Rerun : Re-run Stage 3 & 4
        RefinementA --> S4_Repair : Direct Text Repair di Stage 4
        S3_Rerun --> [*]
        S4_Repair --> [*]
    }

    self_refinement --> grounding_validation : Re-validasi Soal Hasil Refinement (Attempt + 1)

    state "Node 6: Persist Questions & Traces" as persist_questions {
        [*] --> HeuristicCheck : Cek Heuristik Kualitas Non-LLM
        HeuristicCheck --> SaveDB : Simpan ke SQLite (Question, Used Chunks, Traces, & Logs)
        SaveDB --> [*]
    }

    persist_questions --> grounding_validation : Masih Ada Butir Soal Berikutnya (i < Total)
    persist_questions --> [*] : Semua Soal Selesai & Kirim Response Ringkas ke Chat
```

---

## 5. Entity Relationship Diagram (ERD Basis Data Lengkap)

Diagram ini menjelaskan struktur skema tabel relasional SQLite dan relasi antar-entitas data dalam sistem RAG-AQG v4.0.

```mermaid
erDiagram
    DOCUMENTS ||--o{ CHUNKS : "1 Document memiliki N Chunks"
    DOCUMENTS ||--o{ CHAT_SESSIONS : "1 Document memiliki N Chat Sessions"
    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : "1 Session memiliki N Chat Messages"
    CHAT_SESSIONS ||--o{ QUESTIONS : "1 Session menghasilkan N Questions"
    QUESTIONS ||--o{ VALIDATION_LOGS : "1 Question memiliki N Validation Logs"

    DOCUMENTS {
        VARCHAR id PK "UUID Primary Key"
        VARCHAR filename "Nama file PDF asli"
        VARCHAR filepath "Path penyimpanan file di server"
        VARCHAR subject "Mata pelajaran (IPAS/PJOK/PKN/Matematika)"
        VARCHAR status "pending | processing | ready | failed"
        VARCHAR chunking_strategy "section_aware | fixed | semantic"
        TEXT error_message "Log error jika status failed"
        DATETIME uploaded_at "Waktu unggah file"
        DATETIME updated_at "Waktu pembaruan status"
    }

    CHUNKS {
        VARCHAR id PK "UUID Primary Key"
        VARCHAR document_id FK "Foreign Key ke DOCUMENTS.id"
        TEXT text "Konten teks chunk materi"
        VARCHAR category "materi_pokok | uraian_materi | studi_kasus | aktivitas_diskusi | rangkuman"
        VARCHAR section_heading "Judul sub-bab / heading"
        VARCHAR chapter "Identitas bab (misal: Bab 2)"
        INTEGER page_number "Nomor halaman fisik buku asli"
        INTEGER chunk_index "Nomor urutan chunk dalam dokumen"
        VARCHAR section_type "Tipe struktural materi"
        VARCHAR embedding_ref "ID referensi vektor di ChromaDB"
        DATETIME created_at "Waktu pembuatan chunk"
    }

    CHAT_SESSIONS {
        VARCHAR id PK "UUID Primary Key"
        VARCHAR document_id FK "Foreign Key ke DOCUMENTS.id"
        DATETIME created_at "Waktu pembuatan sesi"
    }

    CHAT_MESSAGES {
        VARCHAR id PK "UUID Primary Key"
        VARCHAR session_id FK "Foreign Key ke CHAT_SESSIONS.id"
        VARCHAR role "user | assistant"
        TEXT content "Isi teks percakapan / instruksi"
        DATETIME created_at "Waktu pengiriman pesan"
    }

    QUESTIONS {
        VARCHAR id PK "UUID Primary Key"
        VARCHAR session_id FK "Foreign Key ke CHAT_SESSIONS.id"
        TEXT chunk_ids "JSON List ID Chunk sumber konteks"
        VARCHAR question_type "esai | isian_singkat"
        TEXT question_text "Teks butir pertanyaan (termasuk skenario stimulus)"
        TEXT options "JSON pilihan ganda (opsional)"
        TEXT answer_key "Kunci jawaban ideal komunikatif"
        TEXT explanation "Penjelasan kontekstual edukatif untuk anak SD"
        TEXT source_reference "Referensi Bab, Sub-bab, & Nomor Halaman"
        VARCHAR bloom_level "C1-Mengingat s/d C4-Menganalisis"
        VARCHAR status "final | needs_review"
        INTEGER refinement_count "Jumlah iterasi perbaikan (0-3)"
        TEXT rubric "JSON rubrik kriteria skor bertingkat"
        TEXT answer_elements "JSON elemen kunci jawaban berbobot"
        TEXT grounding_evidence "Kutipan langsung dari buku sumber"
        TEXT knowledge_point "Poin materi spesifik yang diuji"
        TEXT prompt_traces "JSON log transparan eksekusi setiap stage LLM"
        TEXT quality_warnings "JSON list peringatan heuristik non-LLM"
        DATETIME created_at "Waktu generasi soal"
    }

    VALIDATION_LOGS {
        VARCHAR id PK "UUID Primary Key"
        VARCHAR question_id FK "Foreign Key ke QUESTIONS.id"
        INTEGER attempt_number "Nomor percobaan iterasi (1-3)"
        VARCHAR layer "grounding | judge | pre_check"
        VARCHAR score_or_verdict "pass | fail (detail skor similarity / vonis juri)"
        TEXT feedback "Catatan umpan balik perbaikan terarah"
        TEXT aspect_evaluations "JSON rincian evaluasi 5 aspek LLM Judge"
        DATETIME created_at "Waktu pencatatan validasi"
    }
```
