"""Policy KB: 9 topics, stable chunk ids, citations, KB-miss handoff."""
from __future__ import annotations

import pytest

from app.agent.kb import KnowledgeBase
from app.config import ROOT
from eval.checks import citations, scan_violations
from tests.conftest import create_session, send

QUESTIONS = [
    ("多大年龄可以报名骑手", "kb-age", "kb-age-01"),
    ("健康证一般几天能办下来", "kb-health", "kb-health-01"),
    ("装备要自己买吗", "kb-equipment", "kb-equipment-01"),
    ("站点是怎么分布的", "kb-station", "kb-station-01"),
    ("工资怎么计算", "kb-salary", "kb-salary-01"),
    ("平台给骑手买保险吗", "kb-insurance", "kb-insurance-01"),
    ("请假流程是什么", "kb-leave", "kb-leave-01"),
    ("离职要提前几天申请", "kb-resign", "kb-resign-01"),
    ("入职安全培训要多久", "kb-safety", "kb-safety-01"),
]


def test_kb_structure() -> None:
    kb = KnowledgeBase(str(ROOT / "kb" / "docs"))
    docs = {doc["doc_id"] for doc in kb.docs()}
    assert docs == {
        "kb-age", "kb-health", "kb-equipment", "kb-station", "kb-salary",
        "kb-insurance", "kb-leave", "kb-resign", "kb-safety",
    }
    assert len(kb.chunks) == 27
    assert len({chunk.chunk_id for chunk in kb.chunks}) == 27
    topics = {chunk.topic for chunk in kb.chunks}
    assert topics == {
        "age", "health", "equipment", "station", "salary",
        "insurance", "leave", "resignation", "safety",
    }
    for chunk in kb.chunks:
        assert chunk.chunk_id.startswith(f"kb-{chunk.topic[:4] if chunk.topic != 'resignation' else 'resign'}")
        assert chunk.content


@pytest.mark.parametrize(("question", "doc_id", "chunk_id"), QUESTIONS)
def test_policy_answer_has_source(api, question: str, doc_id: str, chunk_id: str) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    reply = send(client, session_id, question)["reply"]
    found = citations(reply)
    assert (doc_id, chunk_id) in found, (question, found)
    assert scan_violations(reply) == []
    assert "保证" not in reply or "不保证" in reply


def test_station_answer_emits_show_stations(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    out = send(client, session_id, "站点是怎么分布的")
    assert "show_stations" in out["actions"]


def test_kb_miss_hands_off(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    out = send(client, session_id, "你们公积金比例是多少")
    assert out["actions"] == ["handoff"]
    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert body["status"] == "handoff"
    assert body["ended_reason"] == "kb_miss"
    assert "（出处" not in out["reply"]


def test_policy_question_does_not_advance_slots(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    out = send(client, session_id, "多大年龄可以报名骑手")
    assert out["progress"]["done"] == 0
