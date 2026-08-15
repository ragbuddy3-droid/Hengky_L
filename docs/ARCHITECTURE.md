# ARCHITECTURE — RAG-AQG v3

## 1. Gambaran Umum Sistem

Sistem RAG-AQG v3 dipisahkan secara bersih antara **Backend API (FastAPI)** dan **Frontend Web Application (Next.js + Mantine UI)**:

1. **Ingestion Pipeline**: Upload PDF → Ekstraksi Teks → PAC Chunking → Embedding (bge-m3) + BM25 Sparse Index → Vector DB & Metadata DB.
2. **Serving & Validation Pipeline**: User Request via Next.js → FastAPI `/api/v1/chat` → State Manager → Hybrid Retrieval → Question Generator → Lapis 1 Grounding Score → Lapis 2 LLM-as-Judge → Refinement Loop (if needed) → Response JSON ke Next.js UI.

---

## 2. Tech Stack v3

| Layer | Teknologi | Catatan |
|---|---|---|
| 1. Package Manager (Backend) | `uv` | Manajemen virtual environment & lockfile Python ultra cepat |
| 2. Backend Framework | FastAPI (Python 3.11+) | Async REST API & CORS Middleware |
| 3. Package Manager & Runtime (Frontend) | `bun` | JavaScript runtime & package manager |
| 4. Frontend Framework | Next.js (App Router, TypeScript) | React Framework modern untuk Web Application |
| 5. UI Component Library | Mantine UI (`@mantine/core`) | Design system & UI components modern |
| 6. RAG Orchestration | LlamaIndex / LangChain | Retrieval, prompt orchestration |
| 7. LLM Inference | Qwen-2.5 / LLaMA-3.1 via Ollama / vLLM | Local LLM inference |
| 8. Embedding & Vector DB | bge-m3 + Qdrant / ChromaDB | Dense vector search |
| 9. Sparse Search | BM25 (rank_bm25) | Keyword search |

---

## 3. Struktur Direktori v3

```text
Testing Program v3/
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   └── src/app/
│       ├── main.py
│       ├── api/v1/
│       ├── core/
│       ├── models/
│       ├── ingestion/
│       ├── retrieval/
│       ├── generation/
│       ├── validation/
│       └── chat/
├── frontend/
│   ├── package.json
│   ├── bun.lockb
│   ├── next.config.ts
│   └── src/
│       ├── app/
│       ├── components/
│       ├── hooks/
│       ├── lib/
│       └── types/
└── docs/
```
