"""In-memory progress events of a running generation, streamed to the frontend over SSE.

Every event is kept, so a subscriber that connects late (e.g. after a page reload) first receives the
full history and then the live events, until the final "done" event.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_RETENTION_SECONDS = 300  # keep a finished run's events so a late subscriber still sees its outcome


@dataclass
class _Run:
    loop: asyncio.AbstractEventLoop
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    done: bool = False


_runs: dict[str, _Run] = {}


def start(session_id: str, target: int) -> None:
    """Begin a new run for the session, replacing the events of a previous one."""
    _runs[session_id] = _Run(loop=asyncio.get_running_loop())
    publish(session_id, {"type": "start", "target": target})


def publish(session_id: str | None, event: dict[str, Any]) -> None:
    """Record an event and push it to live subscribers. A no-op outside a run (e.g. in unit tests).

    Safe to call from worker threads (LangGraph runs sync nodes in an executor): delivery then hops to the loop.
    """
    run = _runs.get(session_id or "")
    if run is None or run.done:
        return
    try:
        on_loop = asyncio.get_running_loop() is run.loop
    except RuntimeError:
        on_loop = False
    if on_loop:
        _deliver(run, event)
    else:
        run.loop.call_soon_threadsafe(_deliver, run, event)


def _deliver(run: _Run, event: dict[str, Any]) -> None:
    if run.done:
        return
    run.events.append(event)
    for queue in run.subscribers:
        queue.put_nowait(event)


def phase(session_id: str | None, name: str, label: str) -> None:
    publish(session_id, {"type": "phase", "phase": name, "label": label})


def candidate(
    session_id: str | None,
    candidate_id: str | None,
    status: str,
    question: dict[str, Any] | None = None,
    attempt: int | None = None,
) -> None:
    """Status change of one candidate question; `question` carries its current text once Stage 4 produced it."""
    if not candidate_id:
        return
    event: dict[str, Any] = {"type": "candidate", "id": candidate_id, "status": status}
    if attempt is not None:
        event["attempt"] = attempt
    if question is not None:
        event["question"] = {
            k: question.get(k)
            for k in ("question", "answer", "bloom_level", "question_type", "source_reference")
        }
    publish(session_id, event)


def finish(session_id: str, status: str, message: str | None = None) -> None:
    """Close the run with a final "done" event; its history is dropped after a while."""
    run = _runs.get(session_id)
    if run is None:
        return
    _deliver(run, {"type": "done", "status": status, "message": message})
    run.done = True

    def _cleanup() -> None:
        if _runs.get(session_id) is run:
            del _runs[session_id]

    run.loop.call_later(_RETENTION_SECONDS, _cleanup)


def discard(session_id: str) -> None:
    """Forget a finished run, so a stream opened for the next run never replays the old outcome."""
    _runs.pop(session_id, None)


def is_active(session_id: str) -> bool:
    return session_id in _runs


async def subscribe(session_id: str) -> AsyncIterator[dict[str, Any] | None]:
    """Yield the run's history, then live events until "done". Yields None after 15 s of silence (heartbeat)."""
    run = _runs.get(session_id)
    if run is None:
        return
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    history = list(run.events)
    run.subscribers.add(queue)
    try:
        for event in history:
            yield event
            if event["type"] == "done":
                return
        if run.done:
            return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield None
                continue
            yield event
            if event["type"] == "done":
                return
    finally:
        run.subscribers.discard(queue)
