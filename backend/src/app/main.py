"""FastAPI application entry point (v3)."""
import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.engine import init_db
from app.config import get_settings
from app.logging_config import setup_logging

from app.api.v1.router import router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("="*60)
    logger.info("RAG-AQG Backend v3 starting up...")
    logger.info("   Generator model : %s", settings.LLM_GENERATOR_MODEL)
    logger.info("   Judge model     : %s", settings.LLM_JUDGE_MODEL)
    logger.info("   Embedding model : %s", settings.EMBEDDING_MODEL)
    logger.info("   Ollama URL      : %s", settings.OLLAMA_BASE_URL)
    logger.info("   Grounding thr.  : %s", settings.GROUNDING_THRESHOLD)
    logger.info("   Max refinement  : %s", settings.MAX_REFINEMENT_ATTEMPTS)
    logger.info("   Database URL    : %s", settings.DATABASE_URL)
    logger.info("   CORS Origins    : %s", settings.CORS_ORIGINS)
    logger.info("="*60)
    init_db()
    logger.info("Database initialized successfully")

    from app.pipeline.service import get_pipeline_service
    get_pipeline_service()
    logger.info("PipelineService initialized successfully")
    yield
    logger.info("RAG-AQG Backend v3 shutting down...")

app = FastAPI(
    title="RAG-AQG API v3",
    description="FastAPI backend for RAG-AQG Automatic Question Generation System",
    version="3.0.0",
    lifespan=lifespan
)

settings = get_settings()
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
    return {"status": "ok", "version": "3.0.0"}

def start():
    """Run uvicorn server."""
    uvicorn.run("app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)

if __name__ == "__main__":
    start()
