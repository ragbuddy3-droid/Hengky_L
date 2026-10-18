"""Tests for per-question validation isolation, final status, Bloom mixing, and question clarity checks."""

import asyncio
import random
from collections import Counter
from typing import Any

import app.graph.nodes as nodes
import app.graph.workflow as workflow
from app.services.generation import planner
from app.services.generation.schemas import (
    ContentAnalysis,
    JudgeAspectResult,
    JudgeEvaluationResult,
    PromptStageTrace,
    QuestionPackage,
)
from app.services.generation.schemas import (
    TestableContentItem as ContentPoint,
)
from app.services.retrieval import retriever
from app.services.validation.quality_checks import (
    find_clarity_issue,
    find_unanswerable_answer,
    validate_answer_quality,
)


def _trace(name: str, attempt: int) -> PromptStageTrace:
    return PromptStageTrace(stage_name=name, attempt_number=attempt, prompt_sent="p", raw_response="{}")


async def _fake_judge(**kwargs: Any):
    ok = "GAGAL" not in kwargs["question"]
    aspect = JudgeAspectResult(status="pass" if ok else "fail", feedback="ok" if ok else "tidak ada di konteks")
    result = JudgeEvaluationResult(
        grounding=aspect,
        overall="pass" if ok else "fail",
        failed_stage="none" if ok else "generation",
    )
    return result, _trace("Layer 2: LLM-as-Judge", kwargs["attempt"])


async def _fake_refinement_a(**kwargs: Any):
    pkg = QuestionPackage(question=kwargs["question"], expected_answer=kwargs["expected_answer"])
    return pkg, _trace("Refinement Prompt A (Generation Repair)", kwargs["attempt"])


def _candidate(text: str, idx: int) -> dict[str, Any]:
    return {
        "question": text,
        "question_type": "esai_pendek",
        "answer": "Jawaban lengkap yang didukung oleh materi buku.",
        "explanation": "Penjelasan.",
        "bloom_level": "C2-Memahami",
        "knowledge_point": f"poin {idx}",
        "grounding_evidence": "kutipan materi buku yang panjang",
        "context": f"konteks soal {idx}",
        "stage_traces": [{"stage_name": f"Stage 4 soal {idx}", "attempt_number": 1}],
        "chunk_id": f"chunk-{idx}",
        "has_fallback": False,
    }


def _build_test_graph(monkeypatch, candidates: list[dict[str, Any]]):
    monkeypatch.setattr(nodes, "run_llm_judge", _fake_judge)
    monkeypatch.setattr(nodes, "run_refinement_a", _fake_refinement_a)
    monkeypatch.setattr(nodes, "get_chat_model", lambda **_: None)
    monkeypatch.setattr(nodes, "get_shared_dense_index", lambda: None)
    monkeypatch.setattr(
        nodes, "compute_grounding_evidence_score",
        lambda **_: {"score": 0.9, "target": "evidence", "is_evidence_based": True},
    )
    monkeypatch.setattr(workflow, "retrieve_context", lambda state: {"retrieved_chunks": [{"id": "x"}]})
    async def fake_generate(state):
        # Stands in for the pipeline: each candidate runs its own validation subgraph (3 attempts as before)
        inputs = [
            {**nodes._validation_input(q, state["session_id"], None, f"r1-{i}"), "max_attempts": 3}
            for i, q in enumerate(candidates)
        ]
        return {"validated_questions": list(await asyncio.gather(*[nodes.validate_candidate(s) for s in inputs]))}

    monkeypatch.setattr(workflow, "generate_questions", fake_generate)
    monkeypatch.setattr(workflow, "top_up_questions", lambda state: {"top_up_done": True})
    monkeypatch.setattr(
        workflow, "persist_questions",
        lambda state: {"finalized_questions": state["validated_questions"]},
    )
    monkeypatch.setattr(workflow, "_validation_graph", None)
    return workflow.build_aqg_graph()


def _run(graph) -> dict[str, Any]:
    return asyncio.run(graph.ainvoke({
        "session_id": "s", "document_id": "d", "user_prompt": "Buatkan 3 soal", "chapter": None,
        "bloom_level": None, "num_questions": 3, "retrieved_chunks": [], "source_chunk_ids": [],
        "reserve_chunks": [], "spare_items": [], "stage_cache": {}, "top_up_done": False,
        "validated_questions": [], "finalized_questions": [], "error": None,
    }))


def test_validation_logs_are_isolated_per_question(monkeypatch):
    candidates = [
        _candidate("Mengapa tumbuhan membutuhkan cahaya matahari?", 0),
        _candidate("GAGAL: Bagaimana cara bermain lempar tangkap melewati net?", 1),
        _candidate("Sebutkan bagian-bagian utama dari bunga sepatu?", 2),
    ]
    final_state = _run(_build_test_graph(monkeypatch, candidates))
    by_kp = {q["knowledge_point"]: q for q in final_state["finalized_questions"]}

    assert len(by_kp) == 3
    for kp in ("poin 0", "poin 2"):
        q = by_kp[kp]
        assert q["status"] == "final"
        assert [log["layer"] for log in q["validation_logs"]] == ["grounding", "judge"]
        # Own generation trace + own judge trace only
        assert [t["stage_name"] for t in q["stage_traces"]] == [f"Stage 4 soal {kp[-1]}", "Layer 2: LLM-as-Judge"]

    failed = by_kp["poin 1"]
    assert len(failed["validation_logs"]) == 6  # 3 attempts x (grounding + judge), nothing from other questions
    assert {log["attempt_number"] for log in failed["validation_logs"]} == {1, 2, 3}


def test_failed_aspect_overrides_overall_pass(monkeypatch):
    async def inconsistent_judge(**kwargs: Any):
        result = JudgeEvaluationResult(
            grounding=JudgeAspectResult(status="fail", feedback="Klaim 'kemiringan poros' tidak ada di CONTEXT."),
            overall="pass",
            failed_stage="none",
        )
        return result, _trace("Layer 2: LLM-as-Judge", kwargs["attempt"])

    graph = _build_test_graph(monkeypatch, [_candidate("Mengapa Venus panas?", 0)])
    monkeypatch.setattr(nodes, "run_llm_judge", inconsistent_judge)
    q = _run(graph)["finalized_questions"][0]

    assert q["status"] == "needs_review"
    judge_logs = [log for log in q["validation_logs"] if log["layer"] == "judge"]
    assert judge_logs[0]["verdict"] == "fail"
    assert "kemiringan poros" in judge_logs[0]["feedback"]
    assert q["refinement_count"] == 2  # failed_stage fell back to "generation" -> Refinement A


def test_question_failing_all_attempts_is_needs_review(monkeypatch):
    final_state = _run(_build_test_graph(monkeypatch, [_candidate("GAGAL: Apa itu net?", 0)]))
    q = final_state["finalized_questions"][0]
    assert q["status"] == "needs_review"
    assert q["refinement_count"] == 2


def test_unclear_question_fails_pre_check(monkeypatch):
    final_state = _run(_build_test_graph(
        monkeypatch, [_candidate("Bagaimana cara bermain bowling sederhana yang telah kamu pelajari?", 0)],
    ))
    q = final_state["finalized_questions"][0]
    assert q["validation_logs"][0]["layer"] == "pre_check"
    assert q["status"] == "needs_review"


def test_mixed_bloom_distribution():
    counts = Counter(planner.assign_bloom_levels(10, None))
    assert counts == {"C1-Mengingat": 3, "C2-Memahami": 3, "C3-Mengaplikasikan": 2, "C4-Menganalisis": 2}
    assert set(planner.assign_bloom_levels(4, "C4-Menganalisis")) == {"C4-Menganalisis"}
    assert set(planner.assign_bloom_levels(2, "C6-Mencipta")) == {"C2-Memahami"}


def test_sanitize_query_without_topic_is_empty():
    assert retriever.sanitize_retrieval_query("Buatkan 10 soal") == ""
    assert retriever.sanitize_retrieval_query("Buatkan 5 soal C4 bab 2") == ""
    assert retriever.sanitize_retrieval_query("buat 3 soal tentang sistem pencernaan") == "sistem pencernaan"


def test_point_lists_drop_duplicates_across_chunks():
    text = "Fungsi akar tumbuhan. Fungsi batang tumbuhan. Proses fotosintesis daun."
    retrieved = [{"id": "a", "text": text}, {"id": "b", "text": text}]
    analyses = {
        "a": ContentAnalysis(testable_content=[
            ContentPoint(point="Fungsi akar tumbuhan", source_quote="Fungsi akar tumbuhan"),
            ContentPoint(point="Fungsi batang tumbuhan", source_quote="Fungsi batang tumbuhan"),
        ]),
        "b": ContentAnalysis(testable_content=[
            ContentPoint(point="Fungsi akar tumbuhan", source_quote="Fungsi akar tumbuhan"),
            ContentPoint(point="Proses fotosintesis daun", source_quote="Proses fotosintesis daun"),
        ]),
    }
    lists = planner.chunk_point_lists(retrieved, analyses)
    assert [[p["point"] for p in points] for points in lists] == [
        ["Fungsi akar tumbuhan", "Fungsi batang tumbuhan"],
        ["Proses fotosintesis daun"],
    ]


def test_select_diverse_chunks_spreads_sections_and_skips_activities():
    chunks = []
    for sec in range(6):
        for j in range(3):
            chunks.append({
                "id": f"{sec}-{j}",
                "text": "Materi pelajaran yang menjelaskan konsep. " * 10,
                "metadata": {"category": "materi_pokok", "chapter": "Bab 1", "section_heading": f"S{sec}",
                             "chunk_index": sec * 3 + j},
            })
    chunks.append({
        "id": "act", "text": "Diskusikan bersama teman. " * 20,
        "metadata": {"category": "aktivitas_diskusi", "chapter": "Bab 1", "section_heading": "Aktivitas", "chunk_index": 99},
    })
    picked = retriever.select_diverse_chunks(chunks, 5, rng=random.Random(0))
    assert len(picked) == 5
    assert len({c["metadata"]["section_heading"] for c in picked}) == 5
    assert all(c["metadata"]["category"] != "aktivitas_diskusi" for c in picked)


def test_quality_checks_accept_imperative_and_flag_vague_questions():
    imperative = {
        "question": "Jelaskan fungsi akar pada tumbuhan.",
        "question_type": "esai",
        "answer": "Akar menyerap air dan unsur hara dari dalam tanah.",
    }
    assert validate_answer_quality(imperative) == []

    assert find_clarity_issue("Jelaskan cara melempar bola seperti yang telah kamu lakukan di kelas.")
    assert find_clarity_issue("Bagaimana cara bermain bowling yang sudah kalian pelajari?")
    assert find_clarity_issue("Jelaskan cara bermainnya? Apa tujuan permainan ini?")
    assert find_clarity_issue("Apa fungsi keranjang dalam permainan bola target yang kamu mainkan?")
    assert find_clarity_issue("Apa yang harus kamu lakukan agar tidak menabrak temanmu?") is None
    assert find_clarity_issue("Mengapa tumbuhan membutuhkan cahaya matahari?") is None


def test_text_referencing_and_unanswerable_questions_are_flagged():
    assert find_clarity_issue("Apa contoh energi kimia yang disebutkan dalam teks?")
    assert find_clarity_issue("Menurut bacaan, apa fungsi akar?")
    assert find_clarity_issue("Apa itu teks prosedur?") is None

    assert find_unanswerable_answer("tidak disebutkan")
    assert find_unanswerable_answer("Nama negaranya tidak dijelaskan dalam teks.")
    assert find_unanswerable_answer("Akar tidak disebutkan sebagai bagian bunga.") is None
    assert find_unanswerable_answer("Lima zona tantangan") is None


def test_unanswerable_question_fails_pre_check(monkeypatch):
    q = _candidate("Negara mana yang dilaporkan berhasil memproduksi 40% listriknya dari tenaga angin?", 0)
    q["answer"] = "tidak disebutkan"
    final_state = _run(_build_test_graph(monkeypatch, [q]))
    logs = final_state["finalized_questions"][0]["validation_logs"]
    assert logs[0]["layer"] == "pre_check"
    assert logs[0]["score_or_verdict"] == "fail (unanswerable)"
