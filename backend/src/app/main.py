"""FastAPI application entry point (v4 / Clean Architecture with LangGraph)."""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.database import get_session, init_db
from app.core.logging_config import setup_logging
from app.graph.nodes import get_chat_model, get_shared_dense_index
from app.graph.workflow import get_aqg_graph
from app.services.chat.session_store import fail_interrupted_generations

logger = logging.getLogger(__name__)


def _prewarm_models() -> None:
    try:
        dense_idx = get_shared_dense_index()
        dense_idx.model.encode(["pemanasan model"], normalize_embeddings=True)
        get_chat_model(is_judge=False)
        get_chat_model(is_judge=True)
        logger.info("Embedding and chat models pre-warmed.")
    except Exception as e:
        logger.warning("Model pre-warm failed (will load lazily): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    setup_logging()
    settings = get_settings()

    logger.info("=" * 60)
    logger.info("RAG-AQG Backend v4 (LangGraph Edition) starting up...")
    logger.info("   Generator model : %s", settings.LLM_GENERATOR_MODEL)
    logger.info("   Judge model     : %s", settings.LLM_JUDGE_MODEL)
    logger.info("   Embedding model : %s", settings.EMBEDDING_MODEL)
    logger.info("   LLM Provider    : %s", settings.LLM_PROVIDER)
    logger.info("   Grounding thr.  : %s", settings.GROUNDING_THRESHOLD)
    logger.info("   Auto-pass thr.  : %s", settings.GROUNDING_AUTO_PASS_THRESHOLD)
    logger.info("   Max refinement  : %s", settings.MAX_REFINEMENT_ATTEMPTS)
    logger.info("   Database URL    : %s", settings.DATABASE_URL)
    logger.info("   CORS Origins    : %s", settings.CORS_ORIGINS)
    logger.info("=" * 60)

    # Initialize Database
    init_db()
    with get_session() as db:
        fail_interrupted_generations(db)
        db.commit()

    # Pre-compile LangGraph StateGraph
    get_aqg_graph()

    # Load the embedding model now instead of during the first generation request (~30s)
    await asyncio.to_thread(_prewarm_models)

    yield
    logger.info("RAG-AQG Backend v4 shutting down...")


settings = get_settings()

app = FastAPI(
    title="RAG-AQG API v4",
    description="FastAPI backend for RAG-AQG Automatic Question Generation System with LangChain & LangGraph",
    version="4.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "4.0.0"}


def start():
    """Run uvicorn server directly with scoped file watching."""
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
        reload_dirs=["src"],
        reload_excludes=[".venv*", "data*", "*.log", "tests*"]
    )


if __name__ == "__main__":
    start()
