"""Shared pytest fixtures: real FastAPI app on a temp SQLite database."""
from __future__ import annotations

from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import create_app

BOOKING_MESSAGES = [
    "我叫王小明，手机号13800138000",
    "1995年3月出生",
    "我想在浦东新区张江镇跑单",
    "全职",
    "有电动车",
    "明天到岗",
    "做过3年配送",
]

CONSENT = {"version": "2026-01", "accepted_at": "2026-10-01T00:00:00+00:00"}


@pytest.fixture
def env(tmp_path) -> Callable[..., tuple[TestClient, Any, Settings]]:
    """Factory: env(llm_fault="timeout") -> (TestClient, app, settings)."""

    def _factory(**overrides: Any) -> tuple[TestClient, Any, Settings]:
        params: dict[str, Any] = {
            "db_mode": "sqlite",
            "sqlite_path": str(tmp_path / "test.db"),
            "audit_dir": str(tmp_path / "audit"),
            "kb_dir": str(ROOT / "kb" / "docs"),
            "llm_mode": "mock",
            "llm_fault": "none",
            "stream_delay_ms": 0,
            "redis_url": "",
        }
        params.update(overrides)
        settings = Settings(**params)
        app = create_app(settings)
        client = TestClient(app)
        return client, app, settings

    return _factory


@pytest.fixture
def api(env) -> Any:
    client, app, settings = env()
    with client:
        yield client, app, settings


def create_session(client: TestClient, channel: str = "test") -> str:
    response = client.post(
        "/api/v1/agent/sessions",
        json={"source_channel": channel, "consent": CONSENT},
    )
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def send(client: TestClient, session_id: str, text: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/messages", json={"text": text}
    )
    assert response.status_code == 200, response.text
    return response.json()


def run_booking(
    client: TestClient,
    messages: list[str] | None = None,
    channel: str = "test",
) -> tuple[str, list[dict[str, Any]]]:
    session_id = create_session(client, channel)
    outputs = [send(client, session_id, text) for text in (messages or BOOKING_MESSAGES)]
    return session_id, outputs
