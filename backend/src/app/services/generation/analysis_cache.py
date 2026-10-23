"""Persistent cache of Stage 1 (Context Understanding) results per chunk.

A chunk's analysis only depends on its text, the Stage 1 prompt, and the generator model, so repeated
requests on the same document reuse it instead of paying for the call again. Fallback results (failed
calls) are never cached.
"""

import hashlib
import json
import logging
from typing import Any

from app.core.config import get_settings
from app.core.database import get_session
from app.models.db_models import ChunkAnalysis
from app.services.generation.prompts import STAGE1_CONTEXT_UNDERSTANDING_PROMPT, SYSTEM_ANALYSIS_PERSONA

logger = logging.getLogger(__name__)


def stage1_prompt_key() -> str:
    raw = f"{get_settings().llm.generator_model}\n{SYSTEM_ANALYSIS_PERSONA}\n{STAGE1_CONTEXT_UNDERSTANDING_PROMPT}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def load_cached_analyses(chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    """{chunk_id: {"analysis": ..., "trace": ...}} for chunks analysed with the current prompt and model."""
    if not chunk_ids:
        return {}
    key = stage1_prompt_key()
    with get_session() as db:
        rows = (
            db.query(ChunkAnalysis)
            .filter(ChunkAnalysis.chunk_id.in_(chunk_ids), ChunkAnalysis.prompt_key == key)
            .all()
        )
        cached = {}
        for row in rows:
            trace = json.loads(row.trace)
            trace["status"] = "cached"
            cached[row.chunk_id] = {"analysis": json.loads(row.analysis), "trace": trace}
        return cached


def store_analyses(entries: dict[str, dict[str, Any]]) -> None:
    """Upsert successful Stage 1 results; entries whose trace is a fallback are skipped."""
    ok = {cid: e for cid, e in entries.items() if not e["trace"].get("has_fallback")}
    if not ok:
        return
    key = stage1_prompt_key()
    try:
        with get_session() as db:
            db.query(ChunkAnalysis).filter(ChunkAnalysis.chunk_id.in_(list(ok))).delete(synchronize_session=False)
            db.add_all([
                ChunkAnalysis(
                    chunk_id=cid,
                    prompt_key=key,
                    analysis=json.dumps(e["analysis"], ensure_ascii=False),
                    trace=json.dumps(e["trace"], ensure_ascii=False),
                )
                for cid, e in ok.items()
            ])
            db.commit()
    except Exception as e:  # the cache is an optimisation; never fail generation because of it
        logger.warning("Failed to cache Stage 1 analyses: %s", e)
