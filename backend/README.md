# RAG-AQG Backend (v4 / backend_new)

Sistem Backend RAG-AQG (Retrieval-Augmented Generation & Automatic Question Generation) berbasis Clean Architecture, FastAPI, LangChain, dan LangGraph.

## Fitur Utama
1. **LangGraph StateGraph Workflow**: Orkestrasi 6 node (Retrieval, Question Generation, Grounding Validation, LLM-as-Judge, Self-Refinement, Database Persistence).
2. **Fixed & Semantic Chunking**: Menggunakan `RecursiveCharacterTextSplitter` dan LangChain `SemanticChunker` dengan model embedding `BAAI/bge-m3`.
3. **Hybrid Retrieval**: Integrasi dense index (ChromaDB) + sparse index (BM25 Okapi) dengan Reciprocal Rank Fusion (RRF) dan runtime anti-exercise filter.
4. **Validasi 2-Layer**:
   - Layer 1: Cosine similarity embedding grounding score (auto-pass >= 0.80).
   - Layer 2: LLM-as-Judge evaluation untuk rubrik kesesuaian soal SD usia 6-12 tahun.
5. **Konfigurasi Murni YAML**: Seluruh konfigurasi disimpan pada `configs/settings.yaml`.

## Cara Menjalankan
```bash
# Pastikan uv terinstal
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
