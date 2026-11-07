"""Hard PII / prompt-injection gates, proven from the audit log."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.agent.guardrails import (
    REFUSAL_REPLY,
    SYSTEM_PROMPT,
    find_id_cards,
    find_phone_numbers,
    scan_pii_counts,
)
from tests.conftest import create_session, send

PII_TEXT = "我叫王小明，手机号13800138000，身份证110101199001011234"
PHONE = "13800138000"
ID_CARD = "110101199001011234"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_pii_never_reaches_model_request(api) -> None:
    client, _app, settings = api
    session_id = create_session(client)
    send(client, session_id, PII_TEXT)
    for text in ("1995年3月出生", "我想在张江跑单", "全职", "有电动车", "明天到岗", "做过3年配送"):
        send(client, session_id, text)

    records = _read_jsonl(Path(settings.audit_dir) / "model_requests.jsonl")
    assert len(records) >= 7
    for record in records:
        serialized = json.dumps(record["payload"], ensure_ascii=False)
        assert PHONE not in serialized
        assert ID_CARD not in serialized
        assert scan_pii_counts(serialized) == {"phone11": 0, "id18": 0}

    # Raw values must still be retrievable server-side (vault), by token.
    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    phone_token = body["collected"]["phone_token"]
    resolved = client.get(f"/api/v1/vault/tokens/{phone_token}").json()
    assert resolved["value"] == PHONE
    name_token = body["collected"]["name_token"]
    assert client.get(f"/api/v1/vault/tokens/{name_token}").json()["value"] == "王小明"

    # Persisted messages are tokenised, never raw.
    connection = sqlite3.connect(settings.sqlite_path)
    try:
        rows = connection.execute(
            "select text from messages where session_id = ?", (session_id,)
        ).fetchall()
    finally:
        connection.close()
    joined = "\n".join(row[0] for row in rows)
    assert PHONE not in joined
    assert ID_CARD not in joined
    assert f"PHONE_TOKEN" in joined
    assert "NAME_TOKEN" in joined


def _injection_cases() -> list[dict]:
    path = Path(__file__).resolve().parent.parent / "eval" / "cases" / "injection.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("case", _injection_cases(), ids=lambda case: case["id"])
def test_injection_is_blocked_without_model_call(api, case: dict) -> None:
    client, _app, settings = api
    session_id = create_session(client)
    for text in case["messages"][:-1]:
        send(client, session_id, text)
    before = len(
        [r for r in _read_jsonl(Path(settings.audit_dir) / "model_requests.jsonl")
         if r["session_id"] == session_id]
    )
    out = send(client, session_id, case["messages"][-1])
    assert out["reply"] == REFUSAL_REPLY
    assert out["actions"] == []
    assert out["progress"]["done"] == case["expect"]["progress_done"]
    after = len(
        [r for r in _read_jsonl(Path(settings.audit_dir) / "model_requests.jsonl")
         if r["session_id"] == session_id]
    )
    assert after == before, "injection must not invoke the model"
    events = _read_jsonl(Path(settings.audit_dir) / "events.jsonl")
    assert any(
        event.get("session_id") == session_id and event.get("event") == "injection_blocked"
        for event in events
    )


def test_injection_count_is_at_least_ten() -> None:
    assert len(_injection_cases()) >= 10


def test_system_prompt_states_hard_constraints() -> None:
    for phrase in ("不越权承诺", "不诱导线下交易", "不索要证件号", "政策回答必须引用", "未满18周岁"):
        assert phrase in SYSTEM_PROMPT


def test_pii_scanners_are_strict() -> None:
    assert find_phone_numbers(PHONE) == [PHONE]
    assert find_phone_numbers("138001380000") == []
    assert find_id_cards(ID_CARD) == [ID_CARD]
