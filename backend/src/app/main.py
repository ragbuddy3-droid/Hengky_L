"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.database import get_session
from app.core.logging_config import setup_logging
from app.core.migrations import init_db
from app.services.auth.accounts import purge_stale_guest_data
from app.services.chat.session_store import fail_interrupted_generations
from app.services.generation.graph.workflow import get_aqg_graph

logger = logging.getLogger(__name__)

_GUEST_PURGE_INTERVAL = 3600  # seconds


async def _purge_guest_data_periodically() -> None:
    """Hapus data tamu yang tidak aktif melewati TTL, saat startup lalu setiap jam."""
    while True:
        try:
            await asyncio.to_thread(purge_stale_guest_data)
        except Exception as e:
            logger.warning("Guest data purge failed: %s", e)
        await asyncio.sleep(_GUEST_PURGE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    setup_logging()

    init_db()
    with get_session() as db:
        fail_interrupted_generations(db)
        db.commit()

    get_aqg_graph()
    purge_task = asyncio.create_task(_purge_guest_data_periodically())

    yield
    purge_task.cancel()
    logger.info("Soalnya backend shutting down...")


app = FastAPI(
    title="Soalnya API",
    description="Soalnya: RAG-based automatic question generation (FastAPI + LangGraph)",
    version="4.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().app.cors_origins or ["*"],
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

