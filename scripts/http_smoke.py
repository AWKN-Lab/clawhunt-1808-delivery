"""Real HTTP smoke test: boot uvicorn on a free port and drive 7 booking turns."""
from __future__ import annotations

import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from app.config import ROOT, Settings
from app.main import create_app

MESSAGES = [
    "我叫王小明，手机号13800138000",
    "1995年3月出生",
    "我想在浦东新区张江镇跑单",
    "全职",
    "有电动车",
    "明天到岗",
    "做过3年配送",
]

REQUIRED_CANDIDATE = [
    "name_token", "phone_token", "birth_ym", "area_text", "job_type",
    "has_ebike", "start_text", "experience_text", "health_cert",
    "source_channel", "status", "consent_version", "consent_at",
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(server: uvicorn.Server, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("uvicorn did not start in time")
        time.sleep(0.05)


def main() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="awkn1808-smoke-"))
    port = _free_port()
    settings = Settings(
        db_mode="sqlite",
        sqlite_path=str(tmp_dir / "smoke.db"),
        audit_dir=str(tmp_dir / "audit"),
        kb_dir=str(ROOT / "kb" / "docs"),
        llm_mode="mock",
        stream_delay_ms=5,
        redis_url="",
    )
    app = create_app(settings)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    failed = 0
    try:
        _wait(server)
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base, timeout=10.0) as client:
            health = client.get("/api/v1/health")
            print(f"GET /api/v1/health -> {health.status_code} {health.json()}")
            if health.status_code != 200:
                failed = 1

            created = client.post(
                "/api/v1/agent/sessions",
                json={
                    "source_channel": "http-smoke",
                    "consent": {
                        "version": "2026-01",
                        "accepted_at": "2026-10-01T00:00:00+00:00",
                    },
                },
            )
            session_id = created.json()["session_id"]
            print(f"POST /api/v1/agent/sessions -> {created.status_code} {created.json()}")

            last = {}
            for index, text in enumerate(MESSAGES, start=1):
                response = client.post(
                    f"/api/v1/agent/sessions/{session_id}/messages",
                    json={"text": text},
                )
                body = response.json()
                last = body
                print(
                    f"[{index}/7] {text} -> {response.status_code} "
                    + json.dumps(
                        {
                            "reply": body["reply"],
                            "progress": body["progress"],
                            "actions": body["actions"],
                        },
                        ensure_ascii=False,
                    )
                )
                if response.status_code != 200:
                    failed = 1

            if last.get("progress", {}).get("done") != 7:
                print("FAIL progress.done != 7")
                failed = 1
            if "booking_confirmed" not in last.get("actions", []):
                print("FAIL booking_confirmed missing")
                failed = 1

            session = client.get(f"/api/v1/agent/sessions/{session_id}").json()
            candidate = session.get("candidate") or {}
            missing = [key for key in REQUIRED_CANDIDATE if candidate.get(key) in (None, "")]
            print(
                "GET /api/v1/agent/sessions/{id} -> "
                + json.dumps(
                    {
                        "status": session["status"],
                        "progress": session["progress"],
                        "candidate": candidate,
                    },
                    ensure_ascii=False,
                )
            )
            if missing:
                print("FAIL candidate missing " + ",".join(missing))
                failed = 1

            # Latency: first response byte <= 2s, first streamed character <= 2.5s.
            stream_session = client.post(
                "/api/v1/agent/sessions",
                json={
                    "source_channel": "latency",
                    "consent": {
                        "version": "2026-01",
                        "accepted_at": "2026-10-01T00:00:00+00:00",
                    },
                },
            ).json()["session_id"]
            started = time.perf_counter()
            first_byte = None
            first_delta = None
            with client.stream(
                "POST",
                f"/api/v1/agent/sessions/{stream_session}/messages/stream",
                json={"text": "我叫王小明"},
            ) as response:
                for line in response.iter_lines():
                    if not line:
                        continue
                    if first_byte is None:
                        first_byte = time.perf_counter() - started
                    if line.startswith("data:") and '"text"' in line and first_delta is None:
                        first_delta = time.perf_counter() - started
                        break
            ttfb = round(first_byte * 1000, 1) if first_byte else 99999
            first_char = round(first_delta * 1000, 1) if first_delta else 99999
            print(
                f"SSE latency -> first_byte={ttfb}ms first_char={first_char}ms "
                f"(limits 2000/2500ms)"
            )
            if ttfb > 2000 or first_char > 2500:
                failed = 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("SMOKE PASS" if failed == 0 else "SMOKE FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
