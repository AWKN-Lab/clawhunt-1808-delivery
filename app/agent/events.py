"""Outbox events with HMAC-SHA256 signatures (no real webhook delivery)."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any


class Outbox:
    def __init__(self, db, secret: str, audit=None) -> None:
        self.db = db
        self.secret = secret
        self.audit = audit

    def signature(self, event_type: str, payload: dict[str, Any], ts: str) -> str:
        canonical = json.dumps(
            {"event": event_type, "payload": payload, "ts": ts},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(
            self.secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    async def emit(
        self, session_id: str | None, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ts = datetime.now(timezone.utc).isoformat()
        signature = self.signature(event_type, payload, ts)
        await self.db.add_outbox(session_id, event_type, payload, signature)
        if self.audit:
            self.audit.event(session_id or "system", "outbox.queued", event_type=event_type)
        return {"event_type": event_type, "signature": signature}
