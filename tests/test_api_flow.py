"""API contract, 7-slot booking loop, SSE, vault and error bodies."""
from __future__ import annotations

import json

from tests.conftest import BOOKING_MESSAGES, CONSENT, create_session, run_booking, send

SLOT_ORDER = [
    "name", "birth_ym", "area_text", "job_type",
    "has_ebike", "start_text", "experience_text",
]


def test_health(api) -> None:
    client, _app, _settings = api
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["llm_mode"] == "mock"
    assert body["kb_docs"] == 9
    assert body["kb_chunks"] == 27


def test_create_session_and_get(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client, "app")
    assert session_id.startswith("s_")
    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert body["status"] == "active"
    assert body["progress"]["done"] == 0
    assert body["progress"]["total"] == 7
    assert body["candidate"] is None
    assert body["ended_reason"] is None


def test_seven_slot_booking_completes(api) -> None:
    client, _app, _settings = api
    session_id, outputs = run_booking(client)
    last = outputs[-1]
    assert last["progress"]["done"] == 7
    assert last["progress"]["fields"] == SLOT_ORDER
    assert "booking_confirmed" in last["actions"]

    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert body["status"] == "completed"
    candidate = body["candidate"]
    for key in (
        "name_token", "phone_token", "birth_ym", "area_text", "job_type",
        "has_ebike", "start_text", "experience_text", "health_cert",
        "source_channel", "status", "consent_version", "consent_at",
    ):
        assert key in candidate
    assert candidate["birth_ym"] == "1995-03"
    assert candidate["area_text"] == "上海市浦东新区张江镇"
    assert candidate["job_type"] == "fulltime"
    assert candidate["has_ebike"] is True
    assert candidate["start_text"] == "明天"
    assert candidate["experience_text"] == "3年"
    assert candidate["source_channel"] == "test"
    assert candidate["status"] == "completed"
    assert candidate["consent_version"] == "2026-01"
    assert candidate["consent_at"].startswith("2026-10-01")


def test_reply_masks_phone_and_name(api) -> None:
    client, _app, _settings = api
    session_id, outputs = run_booking(client)
    assert "138****8000" in outputs[0]["reply"]
    assert "13800138000" not in json.dumps(outputs, ensure_ascii=False)
    assert "王**" in outputs[-1]["reply"]

    body = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert body["collected"]["phone_token"].startswith("PHONE_TOKEN_")
    assert body["collected"]["name_token"].startswith("NAME_TOKEN_")
    assert "phone" not in body["collected"]
    assert "name" not in body["collected"]


def test_vault_tokenize_and_resolve_hides_nothing_on_the_server(api) -> None:
    client, _app, _settings = api
    token = client.post(
        "/api/v1/vault/tokenize", json={"type": "phone", "value": "13800138000"}
    ).json()["token"]
    assert token.startswith("PHONE_TOKEN_")
    resolved = client.get(f"/api/v1/vault/tokens/{token}").json()
    assert resolved == {"type": "phone", "value": "13800138000"}
    missing = client.get("/api/v1/vault/tokens/PHONE_TOKEN_nope")
    assert missing.status_code == 404
    assert missing.json()["code"] == "token_not_found"


def test_vault_rejects_invalid_type(api) -> None:
    client, _app, _settings = api
    response = client.post(
        "/api/v1/vault/tokenize", json={"type": "email", "value": "x@y.z"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_sse_stream_contract(api) -> None:
    client, _app, _settings = api
    session_id = create_session(client)
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/messages/stream",
        json={"text": "我叫王小明"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: meta" in body
    assert "event: delta" in body
    assert "event: done" in body
    done_line = [line for line in body.splitlines() if line.startswith("data: ")][-1]
    payload = json.loads(done_line[len("data: "):])
    assert payload["progress"]["done"] == 1
    assert payload["reply"]


def test_error_body_contract(api) -> None:
    client, _app, _settings = api
    missing = client.get("/api/v1/agent/sessions/s_missing")
    assert missing.status_code == 404
    assert missing.json() == {"code": "session_not_found", "message": "session does not exist"}

    missing_post = client.post(
        "/api/v1/agent/sessions/s_missing/messages", json={"text": "hi"}
    )
    assert missing_post.status_code == 404
    assert missing_post.json()["code"] == "session_not_found"

    invalid = client.post(
        "/api/v1/agent/sessions", json={"source_channel": "x", "consent": {"version": ""}}
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_request"
    assert invalid.json()["message"]

    empty = client.post(
        f"/api/v1/agent/sessions/{create_session(client)}/messages", json={"text": ""}
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "invalid_request"

    unknown_route = client.get("/api/v1/nope")
    assert unknown_route.status_code == 404
    assert unknown_route.json()["code"] == "not_found"


def test_booking_accepts_consent_version(api) -> None:
    client, _app, _settings = api
    response = client.post(
        "/api/v1/agent/sessions",
        json={"source_channel": "mini-program", "consent": CONSENT},
    )
    assert response.status_code == 201
    assert set(response.json()) == {"session_id"}
