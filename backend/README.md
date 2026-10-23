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
uv run fastapi dev        # http://127.0.0.1:8000, auto-reload
# produksi: uv run fastapi run
```

## Struktur Kode (`src/app`)
```
main.py            app FastAPI + lifespan (init DB, purge data tamu)
core/              config (YAML + .env), database, migrations, logging
api/               deps (DbDep, OwnerDep) + router v1: auth, documents, chat, questions
models/            ORM SQLAlchemy 2.0
schemas/           request/response API
services/
  auth/            akun, tamu, kuota, token
  documents.py     simpan & hapus dokumen
  ingestion/       PDF -> chunk -> SQLite + ChromaDB
  retrieval/       dense + BM25 hybrid search
  generation/      pipeline multi-stage + graph/ (LangGraph sesi & validasi per soal)
  chat/            routing intent & diskusi soal
  questions/       penyimpanan soal
  validation/      grounding & quality checks
```
Path relatif di `configs/settings.yaml` (database, chroma, `data/`) selalu dihitung dari folder `backend/`.
