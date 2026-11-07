"""Application service: wires storage, KB, guardrails, engine, and health."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.audit import Audit
from app.agent.engine import DialogueEngine
from app.agent.events import Outbox
from app.agent.kb import KnowledgeBase
from app.agent.vault import Vault
from app.config import Settings
from app.db import Database
from app.errors import ApiError
from app.llm.base import build_llm


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings)
        self.audit = Audit(settings.audit_dir)
        self.kb = KnowledgeBase(settings.kb_dir)
        self.vault = Vault(self.db, self.audit)
        self.llm = build_llm(settings)
        self.outbox = Outbox(self.db, settings.outbox_secret, self.audit)
        self.engine = DialogueEngine(
            self.db, self.kb, self.vault, self.llm, self.audit, self.outbox, settings
        )
        self.kb_chunk_count = 0

    async def start(self) -> None:
        await self.db.init()
        self.kb_chunk_count = await self.db.seed_kb_chunks(self.kb.chunk_rows())

    async def close(self) -> None:
        await self.db.close()

    # ------------------------------------------------------------------
    async def create_session(
        self, source_channel: str, consent_version: str, consent_at: str
    ) -> str:
        session_id = f"s_{uuid.uuid4().hex}"
        await self.db.create_session(
            session_id, source_channel, consent_version, consent_at
        )
        self.audit.event(
            session_id,
            "session.created",
            source_channel=source_channel,
            consent_version=consent_version,
        )
        await self.outbox.emit(
            session_id,
            "candidate.created",
            {
                "session_id": session_id,
                "source_channel": source_channel,
                "consent_version": consent_version,
                "created_at": _now(),
            },
        )
        return session_id

    async def handle_message(self, session_id: str, text: str) -> dict[str, Any]:
        session = await self.db.get_session(session_id)
        if session is None:
            raise ApiError("session_not_found", "session does not exist", 404)
        self.audit.event(session_id, "message.received", text_len=len(text))
        return await self.engine.handle(session, text)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        session = await self.db.get_session(session_id)
        if session is None:
            raise ApiError("session_not_found", "session does not exist", 404)
        from app.agent.engine import _filled_fields
        from app.models import Progress

        fields = _filled_fields(session["collected"])
        return {
            "session_id": session["id"],
            "status": session["status"],
            "progress": Progress(done=len(fields), total=7, fields=fields).model_dump(),
            "collected": session["collected"],
            "candidate": session["candidate"],
            "ended_reason": session["ended_reason"],
            "created_at": session["created_at"],
        }

    async def raw_collected(self, session_id: str) -> dict[str, Any]:
        """Test/eval helper: resolve vault tokens back to raw values."""
        session = await self.db.get_session(session_id)
        if session is None:
            raise ApiError("session_not_found", "session does not exist", 404)
        collected = dict(session["collected"])
        raw: dict[str, Any] = dict(collected)
        for key, out_key in (("name_token", "name"), ("phone_token", "phone")):
            token = collected.get(key)
            if token:
                resolved = await self.vault.resolve(str(token))
                if resolved:
                    raw[out_key] = resolved[1]
        return raw

    async def health(self) -> dict[str, Any]:
        db_ok = await self.db.ping()
        redis_status = "skipped"
        if self.settings.redis_url:
            try:
                import redis.asyncio as redis_async

                client = redis_async.from_url(
                    self.settings.redis_url, socket_timeout=0.5
                )
                await client.ping()
                await client.aclose()
                redis_status = "ok"
            except Exception:
                redis_status = "down"
        return {
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "down",
            "redis": redis_status,
            "llm_mode": self.settings.llm_mode,
            "llm_fault": self.settings.llm_fault,
            "kb_docs": len(self.kb.docs()),
            "kb_chunks": len(self.kb.chunks),
        }
