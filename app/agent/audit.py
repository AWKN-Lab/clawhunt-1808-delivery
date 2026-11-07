"""Append-only JSONL audit: events + every model request payload."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent.guardrails import scan_pii_counts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Audit:
    def __init__(self, audit_dir: str) -> None:
        self.dir = Path(audit_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.model_path = self.dir / "model_requests.jsonl"
        self._lock = threading.Lock()

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def event(self, session_id: str, event: str, **data: Any) -> None:
        self._append(
            self.events_path,
            {"ts": _now(), "session_id": session_id, "event": event, **data},
        )

    def model_request(
        self,
        session_id: str,
        model: str,
        mode: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        counts = scan_pii_counts(serialized)
        record = {
            "ts": _now(),
            "session_id": session_id,
            "model": model,
            "mode": mode,
            "payload": payload,
            "payload_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "pii_counts": counts,
        }
        self._append(self.model_path, record)
        self.event(
            session_id,
            "model.call",
            model=model,
            payload_sha256=record["payload_sha256"],
            pii_counts=counts,
        )
        return record

    def read_events(self) -> list[dict[str, Any]]:
        return self._read(self.events_path)

    def read_model_requests(self) -> list[dict[str, Any]]:
        return self._read(self.model_path)

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
