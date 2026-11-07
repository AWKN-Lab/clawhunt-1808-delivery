"""CI container check: assert a live API completes a 7/7 booking."""
from __future__ import annotations

import json
import os
import sys

import httpx

MESSAGES = [
    "我叫王小明，手机号13800138000",
    "1995年3月出生",
    "我想在浦东新区张江镇跑单",
    "全职",
    "有电动车",
    "明天到岗",
    "做过3年配送",
]

REQUIRED = [
    "name_token", "phone_token", "birth_ym", "area_text", "job_type",
    "has_ebike", "start_text", "experience_text", "health_cert",
    "source_channel", "status", "consent_version", "consent_at",
]


def main() -> int:
    base = os.getenv("API_BASE", "http://127.0.0.1:8000")
    with httpx.Client(base_url=base, timeout=20.0) as client:
        health = client.get("/api/v1/health")
        print(f"health={health.status_code} {health.json()}")
        if health.status_code != 200:
            return 1
        session_id = client.post(
            "/api/v1/agent/sessions",
            json={
                "source_channel": "ci-container",
                "consent": {"version": "2026-01", "accepted_at": "2026-10-01T00:00:00+00:00"},
            },
        ).json()["session_id"]
        last = {}
        for index, text in enumerate(MESSAGES, start=1):
            last = client.post(
                f"/api/v1/agent/sessions/{session_id}/messages", json={"text": text}
            ).json()
            print(f"{index}/7 progress={last['progress']['done']} actions={last['actions']}")
        if last.get("progress", {}).get("done") != 7:
            print("FAIL progress.done != 7")
            return 1
        if "booking_confirmed" not in last.get("actions", []):
            print("FAIL booking_confirmed missing")
            return 1
        session = client.get(f"/api/v1/agent/sessions/{session_id}").json()
        candidate = session.get("candidate") or {}
        print("candidate=" + json.dumps(candidate, ensure_ascii=False))
        missing = [key for key in REQUIRED if candidate.get(key) in (None, "")]
        if missing:
            print("FAIL candidate missing " + ",".join(missing))
            return 1
    print("CONTAINER CHECK PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
