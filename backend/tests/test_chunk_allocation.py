"""Tests for capacity-based chunk selection, per-chunk allocation, focus-only context, and the Stage 1 cache."""

import asyncio
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.graph.nodes as nodes
from app.core.database import Base
from app.models.db_models import Chunk, Document
from app.services.generation import analysis_cache, planner
from app.services.generation.schemas import (
    CognitivePlan,
    ContentAnalysis,
    PromptStageTrace,
    QuestionBlueprint,
    QuestionPackage,
)
from app.services.generation.schemas import (
    TestableContentItem as ContentPoint,
)
from app.services.retrieval import capacity

DENSE_TEXT = (
    "Akar adalah bagian tumbuhan yang berada di dalam tanah. "
    "Akar berfungsi menyerap air dan unsur hara dari dalam tanah. "
    "Batang merupakan jalur pengangkutan air dari akar menuju daun. "
    "Daun disebut dapur tumbuhan karena tempat terjadinya fotosintesis. "
    "Fotosintesis adalah proses pembuatan makanan dengan bantuan cahaya matahari. "
    "Bunga berfungsi sebagai alat perkembangbiakan generatif pada tumbuhan. "
    "Fungsi akar, fungsi batang, fungsi daun, dan fungsi bunga saling mendukung. "
)
THIN_TEXT = "Ayo kita lanjutkan ke bagian berikutnya. Perhatikan gambar di bawah ini dengan saksama ya teman-teman. " * 3
EXERCISE_TEXT = "Latihan soal. Jawablah pertanyaan berikut! 1. Apa fungsi akar? 2. Jelaskan fotosintesis? " * 4


def _chunk(cid: str, text: str = DENSE_TEXT, section: str = "S1", score: float | None = None) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": cid,
        "text": text,
        "metadata": {"category": "materi_pokok", "chapter": "Bab 1", "section_heading": section, "chunk_index": 0},
    }
    if score is not None:
        chunk["rrf_score"] = score
    return chunk


def _analysis(*points: str) -> ContentAnalysis:
    return ContentAnalysis(testable_content=[ContentPoint(point=p, source_quote=p) for p in points])


# ── Stage 0: capacity estimate ──

def test_capacity_estimate():
    assert capacity.estimate_capacity(_chunk("dense")) == 3
    assert capacity.estimate_capacity(_chunk("thin", THIN_TEXT)) == 0
    assert capacity.estimate_capacity(_chunk("ex", EXERCISE_TEXT)) == 0
    assert capacity.estimate_capacity(_chunk("short", "Akar adalah bagian tumbuhan.")) == 0


PROJECT_TEXT = (
    "Proyek Belajar\nTujuan Proyek\nMembuat buku mengenai tata surya.\n"
    "Langkah Pengerjaan Proyek\nSebelum memulai, siapkan buku yang akan menjadi jurnal proyek.\n"
    "Tahap 1: Menentukan Bentuk dan Merencanakan Isi Buku\n"
    "1. Tentukan bentuk buku yang akan kalian buat.\n"
    "2. Buatlah rancangan jumlah halaman beserta isi dan sketsa masing-masing halaman.\n"
    "3. Usahakan kalian memanfaatkan barang-barang bekas dalam pembuatan proyek ini.\n"
)


def test_project_instruction_chunk_has_no_capacity():
    assert capacity.is_project_or_instruction_chunk(PROJECT_TEXT)
    assert capacity.estimate_capacity(_chunk("proj", PROJECT_TEXT)) == 0
    assert not capacity.is_project_or_instruction_chunk(DENSE_TEXT)


def test_select_by_capacity_stops_when_covered_and_skips_empty_chunks():
    ranked = [_chunk("a"), _chunk("thin", THIN_TEXT), _chunk("b"), _chunk("c")]
    selected, rest = capacity.select_by_capacity(ranked, needed=4, max_chunks=10)
    assert [c["id"] for c in selected] == ["a", "b"]  # 3 + 3 >= 4
    assert [c["id"] for c in rest] == ["c"]
    assert all(c["capacity"] == 3 for c in selected)


def test_select_by_capacity_one_question_one_chunk():
    selected, _ = capacity.select_by_capacity([_chunk("a"), _chunk("b")], needed=2, max_chunks=10)
    assert [c["id"] for c in selected] == ["a"]


def test_drop_weak_matches_uses_relative_score():
    ranked = [_chunk("a", score=0.016), _chunk("b", score=0.012), _chunk("c", score=0.006)]
    assert [c["id"] for c in capacity.drop_weak_matches(ranked, 0.5)] == ["a", "b"]


# ── Stage 1 points & allocation ──

def test_points_whose_quote_is_not_in_chunk_are_dropped():
    analysis = ContentAnalysis(testable_content=[
        ContentPoint(point="Fungsi akar", source_quote="Akar berfungsi menyerap air dan unsur hara"),
        ContentPoint(point="Gunung berapi", source_quote="Gunung berapi meletus mengeluarkan lava pijar"),
    ])
    assert [p["point"] for p in planner.valid_points(_chunk("a"), analysis)] == ["Fungsi akar"]


def test_one_chunk_yields_several_questions_with_different_levels():
    lists = planner.chunk_point_lists([_chunk("a")], {"a": _analysis("Fungsi akar", "Proses fotosintesis", "Fungsi bunga")})
    items, spare = planner.allocate_items(lists, planner.assign_bloom_levels(3, None), max_per_chunk=3)
    assert [i["chunk_id"] for i in items] == ["a", "a", "a"]
    assert len({i["bloom_level"] for i in items}) == 3
    assert spare == []


def test_allocation_respects_chunk_capacity_and_rank():
    lists = planner.chunk_point_lists(
        [_chunk("a"), _chunk("b")],
        {"a": _analysis("Fungsi akar", "Fungsi batang", "Fungsi daun"), "b": _analysis("Proses fotosintesis", "Fungsi bunga")},
    )
    items, spare = planner.allocate_items(lists, planner.assign_bloom_levels(3, None), max_per_chunk=2)
    assert [i["chunk_id"] for i in items] == ["a", "b", "a"]
    assert [s["point"] for s in spare] == ["Fungsi bunga", "Fungsi daun"]


def test_points_are_reused_only_when_everything_is_used():
    lists = planner.chunk_point_lists([_chunk("a")], {"a": _analysis("Fungsi akar")})
    items, _ = planner.allocate_items(lists, planner.assign_bloom_levels(3, None), max_per_chunk=3)
    assert [i["point"] for i in items] == ["Fungsi akar"] * 3
    assert len({i["bloom_level"] for i in items}) == 3


def test_focus_context_is_the_chunk_only():
    assert planner.focus_context(_chunk("a")) == DENSE_TEXT


# ── Node 2 / top-up with fake LLM stages ──

def _trace(name: str) -> PromptStageTrace:
    return PromptStageTrace(stage_name=name, prompt_sent="p", raw_response="{}")


class _Calls:
    def __init__(self) -> None:
        self.stage1: list[str] = []
        self.stage3: list[int] = []
        self.stage4_context: list[str] = []
        self.validated: list[str] = []


def _patch_stages(monkeypatch, points_by_text: dict[str, tuple[str, ...]], status: str = "needs_review") -> _Calls:
    calls = _Calls()

    async def fake_validate(state):
        # Later candidates take longer, as real judge calls finish at different times
        await asyncio.sleep(0.05 * int(state["candidate_id"].split("-")[1]))
        calls.validated.append(state["candidate_id"])
        return {**state["question"], "status": status, "validation_logs": [], "stage_traces": state["stage_traces"]}

    async def fake_stage1(_model, text, _attempt):
        calls.stage1.append(text)
        return _analysis(*points_by_text.get(text, ())), _trace("Stage 1")

    async def fake_stage2(_model, _summary, level, _attempt):
        return CognitivePlan(cognitive_level=level), _trace("Stage 2")

    async def fake_stage3_batch(_model, _text, items, _plans, _attempt):
        calls.stage3.append(len(items))
        return [QuestionBlueprint(knowledge_point=it["point"]) for it in items], [False] * len(items), _trace("Stage 3")

    async def fake_stage4(_model, context, blueprint, level, _q_type, _few, _attempt):
        calls.stage4_context.append(context)
        pkg = QuestionPackage(question=f"Jelaskan {blueprint.knowledge_point} ({level})?", expected_answer="A")
        return pkg, _trace("Stage 4")

    monkeypatch.setattr(nodes, "run_stage1_context_understanding", fake_stage1)
    monkeypatch.setattr(nodes, "run_stage2_cognitive_planning", fake_stage2)
    monkeypatch.setattr(nodes, "run_stage3_blueprint_batch", fake_stage3_batch)
    monkeypatch.setattr(nodes, "run_stage4_question_generation", fake_stage4)
    monkeypatch.setattr(nodes, "validate_candidate", fake_validate)
    monkeypatch.setattr(nodes, "get_chat_model", lambda **_: None)
    monkeypatch.setattr(nodes, "load_few_shots", lambda _doc, levels: dict.fromkeys(levels, planner.NO_FEW_SHOT))
    monkeypatch.setattr(nodes, "load_cached_analyses", lambda _ids: {})
    monkeypatch.setattr(nodes, "store_analyses", lambda _entries: None)
    return calls


def test_generate_batches_stage3_per_chunk_and_expands_when_short(monkeypatch):
    text_b = DENSE_TEXT + "Biji tumbuh menjadi tumbuhan baru."
    calls = _patch_stages(monkeypatch, {
        DENSE_TEXT: ("Fungsi akar", "Proses fotosintesis"),
        text_b: ("Fungsi bunga",),
    })
    state: Any = {
        "document_id": "doc", "num_questions": 2, "bloom_level": None,
        "retrieved_chunks": [_chunk("a")], "reserve_chunks": [_chunk("b", text_b)],
    }
    out = asyncio.run(nodes.generate_questions(state))

    assert len(calls.stage1) == 2  # chunk "a" only had 2 points for 3 candidates -> reserve chunk "b" analysed
    assert sorted(calls.stage3) == [1, 2]  # one Stage 3 call per chunk
    assert len(calls.stage4_context) == 3
    assert set(calls.stage4_context) == {DENSE_TEXT, text_b}  # each question sees only its own chunk
    assert out["reserve_chunks"] == []
    assert {q["chunk_id"] for q in out["validated_questions"]} == {"a", "b"}
    assert len(calls.validated) == 3  # every candidate is validated right after Stage 4


def test_generation_stops_once_enough_questions_are_final(monkeypatch):
    calls = _patch_stages(monkeypatch, {DENSE_TEXT: ("Fungsi akar", "Proses fotosintesis", "Fungsi daun")}, status="final")
    state: Any = {
        "document_id": "doc", "num_questions": 1, "bloom_level": None,
        "retrieved_chunks": [_chunk("a")], "reserve_chunks": [],
    }
    out = asyncio.run(nodes.generate_questions(state))

    assert len(out["validated_questions"]) == 1  # 2 candidates were planned; the second is cancelled
    assert len(calls.validated) == 1


def test_top_up_analyses_reserve_chunk(monkeypatch):
    text_r = DENSE_TEXT + "Biji tumbuh menjadi tumbuhan baru."
    calls = _patch_stages(monkeypatch, {text_r: ("Fungsi akar", "Proses fotosintesis")})
    trace = _trace("t").model_dump()
    state: Any = {
        "document_id": "doc",
        "num_questions": 3,
        "bloom_level": "C2-Memahami",
        "retrieved_chunks": [_chunk("a")],
        "reserve_chunks": [_chunk("r1", text_r)],
        "spare_items": [],
        "stage_cache": {
            "analyses": {"a": {"analysis": _analysis("Fungsi bunga").model_dump(), "trace": trace}},
            "plans": {"C2-Memahami": {"plan": CognitivePlan().model_dump(), "trace": trace}},
            "few_shots": {"C2-Memahami": planner.NO_FEW_SHOT},
        },
        "validated_questions": [
            {"question": "Sebutkan fungsi bunga?", "status": "final", "bloom_level": "C2-Memahami",
             "knowledge_point": "Fungsi bunga", "chunk_id": "a"},
            {"question": "Apa itu bunga?", "status": "needs_review", "bloom_level": "C2-Memahami",
             "knowledge_point": "Fungsi bunga", "chunk_id": "a", "grounding_evidence": "Bunga berfungsi"},
        ],
    }

    out = asyncio.run(nodes.top_up_questions(state))

    assert len(calls.stage1) == 1  # only the reserve chunk is analysed; chunk "a" is cached
    assert [c["id"] for c in out["retrieved_chunks"]] == ["a", "r1"]
    assert out["reserve_chunks"] == []
    points = {q["knowledge_point"]: q["chunk_id"] for q in out["validated_questions"]}
    assert points["Fungsi akar"] == "r1" and points["Proses fotosintesis"] == "r1"


# ── Persistent Stage 1 cache ──

def test_stage1_cache_roundtrip(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)

    @contextmanager
    def fake_get_session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(analysis_cache, "get_session", fake_get_session)
    with fake_get_session() as db:
        db.add(Document(id="d", filename="b.pdf", subject="IPAS"))
        db.add_all([Chunk(id="c1", document_id="d", text="x"), Chunk(id="c2", document_id="d", text="y")])
        db.commit()

    ok_trace = _trace("Stage 1").model_dump()
    bad_trace = {**ok_trace, "status": "fallback", "has_fallback": True}
    analysis_cache.store_analyses({
        "c1": {"analysis": _analysis("Fungsi akar").model_dump(), "trace": ok_trace},
        "c2": {"analysis": _analysis("x").model_dump(), "trace": bad_trace},
    })

    cached = analysis_cache.load_cached_analyses(["c1", "c2"])
    assert list(cached) == ["c1"]  # fallback results are not cached
    assert cached["c1"]["trace"]["status"] == "cached"
    assert ContentAnalysis.model_validate(cached["c1"]["analysis"]).testable_content[0].point == "Fungsi akar"
