"""Terminal paths, downgrade on model faults, and outbox events."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.agent.events import Outbox
from app.agent.guardrails import REFUSAL_REPLY  # noqa: F401  (import parity with runtime)
from tests.conftest import create_session, send

MINOR_MESSAGES = ["我叫张三", "2012年8月出生", "我想做全职"]


def test_minor_ends_immediately(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    send(client, session_id, "我叫张三")
    out = send(client, session_id, "2012年8月出生")
    assert out["actions"] == ["end_minor"]
    assert "未满18" in out["reply"]
    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert body["status"] == "end_minor"
    assert body["ended_reason"] == "minor"
    assert body["progress"]["done"] == 2

    after = send(client, session_id, "我想做全职")
    assert after["actions"] == ["end_minor"]
    assert after["progress"]["done"] == 2
    assert client.get(f"/api/v1/agent/sessions/{session_id}").json()["status"] == "end_minor"


@pytest.mark.parametrize(
    "text",
    [
        "我要投诉你们站点乱收费",
        "我刚才送单摔伤了",
        "我出车祸了，现在在医院",
        "工资太低了，能不能加钱",
        "加你微信聊吧",
        "能不能私下转账",
        "我要转人工",
    ],
)
def test_handoff_triggers(api, text: str) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    out = send(client, session_id, text)
    assert out["actions"] == ["handoff"]
    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert body["status"] == "handoff"
    assert body["ended_reason"] in {"complaint", "accident", "price", "offline_trade", "user_request"}


def test_safety_policy_is_not_treated_as_accident_handoff(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    out = send(client, session_id, "送单路上摔伤怎么办")
    assert out["actions"] == []
    assert "kb-safety-02" in out["reply"]


@pytest.mark.parametrize("fault", ["timeout", "error"])
def test_model_fault_degrades_without_losing_progress(env, fault: str) -> None:
    client, _app, _settings = env(llm_fault=fault)
    with client:
        session_id = create_session(client)
        first = send(client, session_id, "我叫王小明")
        assert "模型服务暂时不可用" in first["reply"]
        assert "handoff" in first["actions"]
        assert first["progress"]["done"] == 1
        body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
        assert body["status"] == "active", "downgrade must not clear the session"

        second = send(client, session_id, "1995年3月出生")
        assert second["progress"]["done"] == 2

        for text in ("我想在张江跑单", "全职", "有电动车", "明天到岗", "做过3年配送"):
            last = send(client, session_id, text)
        assert last["progress"]["done"] == 7
        assert "booking_confirmed" in last["actions"]
        assert "handoff" in last["actions"]

        events = [
            json.loads(line)
            for line in (_settings.audit_dir and open(
                f"{_settings.audit_dir}/events.jsonl", encoding="utf-8"
            ).read().splitlines())
            if line.strip()
        ]
        assert any(
            event.get("event") == "model.fault" and event.get("session_id") == session_id
            for event in events
        )
        body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
        assert body["status"] == "completed"
        assert body["candidate"]["birth_ym"] == "1995-03"


def test_outbox_events_have_hmac_signature(api) -> None:
    client, _app, settings = api
    session_id = create_session(client)
    for text in ("我叫王小明", "1995年3月出生", "我想在张江跑单", "全职", "有电动车", "明天到岗", "做过3年配送"):
        send(client, session_id, text)
    handoff_session = create_session(client)
    send(client, handoff_session, "我要投诉")

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        rows = connection.execute(
            "select event_type, signature from outbox order by id"
        ).fetchall()
    finally:
        connection.close()
    event_types = {row[0] for row in rows}
    assert event_types >= {"candidate.created", "candidate.completed", "handoff.requested"}
    for _event_type, signature in rows:
        assert len(signature) == 64
        int(signature, 16)


def test_outbox_signature_is_deterministic() -> None:
    outbox = Outbox(db=None, secret="secret")
    first = outbox.signature("candidate.completed", {"a": 1}, "2026-01-01T00:00:00Z")
    second = outbox.signature("candidate.completed", {"a": 1}, "2026-01-01T00:00:00Z")
    assert first == second
    other = Outbox(db=None, secret="other").signature(
        "candidate.completed", {"a": 1}, "2026-01-01T00:00:00Z"
    )
    assert other != first
