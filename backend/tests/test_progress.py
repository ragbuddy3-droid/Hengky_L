"""Tests for the in-memory generation progress hub behind the SSE stream."""

import asyncio

from app.services.generation import progress


def test_late_subscriber_gets_history_then_live_events():
    async def scenario() -> list[dict]:
        progress.start("s1", target=2)
        progress.phase("s1", "analysis", "Menganalisis…")
        progress.candidate("s1", "r1-1", "validating", {"question": "Apa fungsi akar?"}, attempt=1)

        received: list[dict] = []

        async def consume() -> None:
            async for event in progress.subscribe("s1"):
                received.append(event)

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0)
        # Sync LangGraph nodes publish from worker threads
        await asyncio.to_thread(progress.candidate, "s1", "r1-1", "final", {"question": "Apa fungsi akar?"})
        await asyncio.sleep(0)
        progress.finish("s1", "done")
        await asyncio.wait_for(consumer, timeout=1)
        progress.discard("s1")
        return received

    events = asyncio.run(scenario())
    assert [e["type"] for e in events] == ["start", "phase", "candidate", "candidate", "done"]
    assert events[2]["question"]["question"] == "Apa fungsi akar?"
    assert events[3]["status"] == "final"


def test_publish_without_run_is_a_noop():
    progress.candidate("no-run", "r1-1", "final")
    assert not progress.is_active("no-run")
