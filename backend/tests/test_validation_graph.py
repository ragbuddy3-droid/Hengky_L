"""Tests for per-question validation isolation, final status, Bloom mixing, and question clarity checks."""

import asyncio
import random
from collections import Counter
from typing import Any

import app.graph.nodes as nodes
import app.graph.workflow as workflow
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
from app.services.validation.quality_checks import find_clarity_issue, validate_answer_quality


def _trace(name: str, attempt: int) -> PromptStageTrace:
    return PromptStageTrace(stage_name=name, attempt_number=attempt, prompt_sent="p", raw_response="{}")


def _fake_judge(**kwargs: Any):
    ok = "GAGAL" not in kwargs["question"]
    aspect = JudgeAspectResult(status="pass" if ok else "fail", feedback="ok" if ok else "tidak ada di konteks")
    result = JudgeEvaluationResult(
        grounding=aspect,
        overall="pass" if ok else "fail",
        failed_stage="none" if ok else "generation",
    )
    return result, _trace("Layer 2: LLM-as-Judge", kwargs["attempt"])


def _fake_refinement_a(**kwargs: Any):
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
    monkeypatch.setattr(workflow, "generate_questions", lambda state: {"raw_questions": candidates})
    monkeypatch.setattr(workflow, "top_up_questions", lambda state: {"raw_questions": [], "top_up_done": True})
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
        "chat_history": "", "raw_questions": [], "spare_items": [], "stage_cache": {}, "top_up_done": False,
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
    counts = Counter(nodes.assign_bloom_levels(10, None))
    assert counts == {"C1-Mengingat": 3, "C2-Memahami": 3, "C3-Mengaplikasikan": 2, "C4-Menganalisis": 2}
    assert set(nodes.assign_bloom_levels(4, "C4-Menganalisis")) == {"C4-Menganalisis"}
    assert set(nodes.assign_bloom_levels(2, "C6-Mencipta")) == {"C2-Memahami"}


def test_sanitize_query_without_topic_is_empty():
    assert nodes.sanitize_retrieval_query("Buatkan 10 soal") == ""
    assert nodes.sanitize_retrieval_query("Buatkan 5 soal C4 bab 2") == ""
    assert nodes.sanitize_retrieval_query("buat 3 soal tentang sistem pencernaan") == "sistem pencernaan"


def test_item_specs_interleave_chunks_and_drop_duplicates():
    retrieved = [{"id": "a"}, {"id": "b"}]
    analyses = {
        "a": ContentAnalysis(testable_content=[
            ContentPoint(point="Fungsi akar tumbuhan", source_quote="q"),
            ContentPoint(point="Fungsi batang tumbuhan", source_quote="q"),
        ]),
        "b": ContentAnalysis(testable_content=[
            ContentPoint(point="Fungsi akar tumbuhan", source_quote="q"),
            ContentPoint(point="Proses fotosintesis daun", source_quote="q"),
        ]),
    }
    specs = nodes.build_item_specs(retrieved, analyses)
    assert [(s["chunk_id"], s["point"]) for s in specs] == [
        ("a", "Fungsi akar tumbuhan"),
        ("a", "Fungsi batang tumbuhan"),
        ("b", "Proses fotosintesis daun"),
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
    picked = nodes.select_diverse_chunks(chunks, 5, rng=random.Random(0))
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
