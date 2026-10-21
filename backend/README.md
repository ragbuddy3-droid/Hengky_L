# Soalnya — Backend

Backend Soalnya, sistem RAG-AQG (Retrieval-Augmented Generation for Automatic Question Generation) berbasis FastAPI dan LangGraph.

## Fitur Utama
1. **LangGraph Workflow**: retrieval konteks → generasi soal multi-stage → validasi per soal (grounding, LLM-as-Judge, self-refinement) → top-up → penyimpanan ke database.
2. **Fixed-size Chunking**: jendela karakter tetap (`fixed_chunk_size` / `fixed_chunk_overlap` di `configs/settings.yaml`) dengan metadata bab dan heading.
3. **Hybrid Retrieval**: dense index (ChromaDB, embedding `BAAI/bge-m3` lewat API DeepInfra) + sparse index (BM25 Okapi) dengan Reciprocal Rank Fusion dan filter latihan/rubrik penilaian buku.
4. **Validasi 2-Layer**:
   - Layer 1: grounding similarity (fast-reject di bawah `fast_reject_threshold`).
   - Layer 2: LLM-as-Judge untuk kesesuaian soal SD usia 6-12 tahun.
5. **Konfigurasi YAML + .env**: konfigurasi di `configs/settings.yaml`, API key (`DEEPINFRA_API_KEY`) di `.env`.
6. **LLM Provider**: DeepInfra (model generator dan judge diatur di `configs/settings.yaml`) dengan output JSON terstruktur.

## Cara Menjalankan
```bash
# Pastikan uv terinstal
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
