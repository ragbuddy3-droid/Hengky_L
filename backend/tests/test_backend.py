"""Unit and integration tests for backend_new."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings
from app.services.ingestion.factory import get_chunker, chunk_text, ChunkerStrategy
from app.services.retrieval.sparse_index import SparseIndex
from app.services.retrieval.hybrid_search import reciprocal_rank_fusion

client = TestClient(app)


def test_health_endpoints():
    """Verify health and root endpoints."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json() == {"status": "ok", "version": "4.0.0"}

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok", "version": "4.0.0"}


def test_settings_pure_yaml():
    """Verify settings loaded properly from YAML."""
    settings = get_settings()
    assert settings.app.backend_port == 8000
    assert settings.llm.provider in ("groq", "ollama")
    assert settings.validation.grounding_auto_pass_threshold == 0.80
    assert settings.chunking.fixed_chunk_size == 1000


def test_fixed_chunker():
    """Verify Fixed Chunker splits text and extracts categories."""
    sample_text = (
        "Bab 1 Sistem Pernapasan Manusia\n"
        "Organ pernapasan manusia adalah hidung, tenggorokan, dan paru-paru. "
        "Paru-paru berfungsi untuk menukar oksigen dan karbon dioksida. " * 15
    )
    chunks = chunk_text(sample_text, strategy="fixed")
    assert len(chunks) >= 1
    assert chunks[0].category == "Konsep"
    assert "Bab 1" in str(chunks[0].chapter)


def test_semantic_chunker():
    """Verify Semantic Chunker produces chunks with embeddings."""
    sample_text = (
        "Bab 2 Pencernaan Makanan\n"
        "Makanan masuk melalui mulut kemudian dikunyah oleh gigi. "
        "Enzim ptialin membantu mencerna karbohidrat di mulut.\n\n"
        "Selanjutnya makanan didorong melewati kerongkongan menuju lambung. "
        "Di dalam lambung, asam klorida membunuh kuman penyakit."
    )
    chunks = chunk_text(sample_text, strategy="semantic")
    assert len(chunks) >= 1
    assert chunks[0].text is not None


def test_sparse_bm25_and_rrf():
    """Verify BM25 Okapi and RRF ranking logic."""
    chunks = [
        {"id": "c1", "text": "Hidung adalah organ pernapasan utama pada manusia.", "metadata": {}},
        {"id": "c2", "text": "Jantung memompa darah ke seluruh tubuh manusia.", "metadata": {}},
    ]
    sparse = SparseIndex()
    sparse.build_index(chunks)
    res = sparse.query("organ pernapasan hidung", top_k=2)
    assert len(res) >= 1
    assert res[0]["id"] == "c1"

    dense_res = [{"id": "c1", "score": 0.9}, {"id": "c2", "score": 0.4}]
    sparse_res = [{"id": "c1", "score": 2.5}, {"id": "c2", "score": 0.1}]
    fused = reciprocal_rank_fusion(dense_res, sparse_res, k=60)
    assert fused[0]["id"] == "c1"
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]


def test_api_routes_listing():
    """Verify API v1 endpoints respond with expected schema."""
    # List documents
    res_docs = client.get("/api/v1/documents/")
    assert res_docs.status_code == 200
    assert isinstance(res_docs.json(), list)

    # List chat sessions
    res_sessions = client.get("/api/v1/chat/sessions")
    assert res_sessions.status_code == 200
    assert isinstance(res_sessions.json(), list)

    # List questions
    res_questions = client.get("/api/v1/questions/")
    assert res_questions.status_code == 200
    assert isinstance(res_questions.json(), list)
