"""Unit and integration tests for backend_new."""

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.ingestion.factory import chunk_text
from app.services.retrieval.hybrid_search import reciprocal_rank_fusion
from app.services.retrieval.sparse_index import SparseIndex

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
    """Verify settings loaded properly from YAML and .env."""
    settings = get_settings()
    assert settings.app.backend_port == 8000
    assert settings.llm.provider == "deepinfra"
    assert settings.llm.generator_model == "Qwen/Qwen3-32B"
    assert settings.llm.judge_model == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    assert settings.llm.deepinfra_base_url == "https://api.deepinfra.com/v1/openai"
    assert settings.validation.fast_reject_threshold == 0.40
    assert settings.chunking.strategy == "section_aware"
    assert settings.retrieval.candidate_top_k == 15
    assert settings.retrieval.reranker_enabled is True


def test_deepinfra_chat_model_initialization():
    """Verify get_chat_model initializes ChatOpenAI with DeepInfra and JSON structured output."""
    from app.graph.nodes import get_chat_model

    gen_model = get_chat_model(is_judge=False)
    assert gen_model.model_name == "Qwen/Qwen3-32B"
    assert "deepinfra.com" in str(gen_model.openai_api_base)
    assert gen_model.model_kwargs.get("response_format") == {"type": "json_object"}
    assert gen_model.max_tokens == 4096

    judge_model = get_chat_model(is_judge=True)
    assert judge_model.model_name == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    assert "deepinfra.com" in str(judge_model.openai_api_base)
    assert judge_model.model_kwargs.get("response_format") == {"type": "json_object"}
    assert judge_model.max_tokens == 4096


def test_section_aware_chunker():
    """Verify SectionAwareChunker preserves structure, chapter, heading, and page metadata."""
    from app.services.ingestion.extractor import PageContent

    sample_page_1 = PageContent(
        page_number=12,
        text=(
            "BAB 2: SISTEM PENCERNAAN MANUSIA\n\n"
            "A. Organ-Organ Pencernaan\n"
            "Makanan yang kita makan akan dicerna oleh sistem pencernaan untuk menghasilkan energi tubuh. "
            "Proses pencernaan dimulai dari rongga mulut tempat makanan dihancurkan secara mekanik dan kimiawi. "
            "Gigi berfungsi menghaluskan makanan sedangkan kelenjar ludah menghasilkan enzim ptialin untuk mencerna karbohidrat."
        )
    )
    sample_page_2 = PageContent(
        page_number=13,
        text=(
            "Setelah dari mulut, makanan melewati kerongkongan melalui gerakan peristaltik menuju lambung.\n\n"
            "Di dalam lambung, makanan diaduk dan dicampur dengan asam lambung (HCl) yang berfungsi membunuh bakteri serta mengaktifkan enzim pepsin."
        )
    )

    from app.services.ingestion.chunkers.section_aware_chunker import SectionAwareChunker
    chunker = SectionAwareChunker(target_words_min=30, target_words_max=100, overlap_sentences=1)
    chunks = chunker.chunk_pages([sample_page_1, sample_page_2])

    assert len(chunks) >= 1
    assert "Bab 2" in str(chunks[0].chapter)
    assert chunks[0].page_number in (12, 13)
    assert chunks[0].section_type in ("materi_pokok", "uraian_materi")
    assert chunks[0].chunk_index == 0


def test_fixed_and_semantic_factory_fallback():
    """Verify factory dispatches to SectionAwareChunker as default."""
    sample_text = (
        "Bab 1 Sistem Pernapasan Manusia\n"
        "Organ pernapasan manusia adalah hidung, tenggorokan, dan paru-paru. "
        "Paru-paru berfungsi untuk menukar oksigen dan karbon dioksida. " * 5
    )
    chunks = chunk_text(sample_text)
    assert len(chunks) >= 1
    assert "Bab 1" in str(chunks[0].chapter)


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
