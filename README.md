# Soalnya — Soal otomatis dari buku

Soalnya adalah sistem RAG-AQG (Retrieval-Augmented Generation for Automatic Question Generation): membuat soal dari buku pelajaran dan memvalidasinya terhadap isi buku.

## Technology Stack

- **Backend**: FastAPI (Python 3.11+), managed by [`uv`](https://github.com/astral-sh/uv).
- **Frontend**: Next.js (App Router, TypeScript) + Mantine UI (`@mantine/core`), managed by [`bun`](https://bun.sh).
- **LLM & Embeddings**: DeepInfra (OpenAI-compatible API) untuk generator dan judge + BAAI/bge-m3 dense embeddings + BM25 sparse index.
- **Vector DB**: ChromaDB.

## Project Layout

```text
Testing Program v3/
├── backend/          # FastAPI App (uv)
├── frontend/         # Next.js App Router + Mantine UI (bun)
├── docs/             # PRD & Architecture Documentation
├── data/             # Local PDFs, DBs & Vector Storage
└── README.md
```

## Quick Start

### 1. Backend Setup (FastAPI with `uv`)
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup (Next.js with `bun`)
```bash
cd frontend
bun install
bun dev
```

Akses frontend di `http://localhost:3000` dan FastAPI Swagger UI di `http://localhost:8000/docs`.
