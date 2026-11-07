"""Storage layer: SQLAlchemy async core with SQLite (local) / PostgreSQL (compose)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Integer, String, Text, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import Settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_at: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    collected: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    candidate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    pii_masked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class VaultRow(Base):
    __tablename__ = "vault_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class OutboxRow(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class KbChunkRow(Base):
    __tablename__ = "kb_chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    heading: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def _row_to_dict(row: SessionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "source_channel": row.source_channel,
        "consent_version": row.consent_version,
        "consent_at": row.consent_at,
        "status": row.status,
        "collected": dict(row.collected or {}),
        "candidate": dict(row.candidate) if row.candidate else None,
        "ended_reason": row.ended_reason,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = None
        self._maker: async_sessionmaker[AsyncSession] | None = None

    @property
    def dsn(self) -> str:
        if self.settings.db_mode == "sqlite":
            Path(self.settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return self.settings.dsn

    async def init(self) -> None:
        self.engine = create_async_engine(self.dsn, future=True, pool_pre_ping=True)
        self._maker = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        if self._maker is None:
            raise RuntimeError("database is not initialised")
        return self._maker()

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None

    async def ping(self) -> bool:
        try:
            async with self.session() as session:
                await session.execute(select(1))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    async def create_session(
        self,
        session_id: str,
        source_channel: str,
        consent_version: str,
        consent_at: str,
    ) -> dict[str, Any]:
        now = _now()
        row = SessionRow(
            id=session_id,
            source_channel=source_channel,
            consent_version=consent_version,
            consent_at=consent_at,
            status="active",
            collected={},
            candidate=None,
            ended_reason=None,
            created_at=now,
            updated_at=now,
        )
        async with self.session() as session:
            session.add(row)
            await session.commit()
        return _row_to_dict(row)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        async with self.session() as session:
            row = await session.get(SessionRow, session_id)
            return _row_to_dict(row) if row else None

    async def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        collected: dict | None = None,
        candidate: dict | None = None,
        ended_reason: str | None = None,
    ) -> dict[str, Any] | None:
        async with self.session() as session:
            row = await session.get(SessionRow, session_id)
            if row is None:
                return None
            if status is not None:
                row.status = status
            if collected is not None:
                row.collected = dict(collected)
            if candidate is not None:
                row.candidate = dict(candidate)
            if ended_reason is not None:
                row.ended_reason = ended_reason
            row.updated_at = _now()
            await session.commit()
            return _row_to_dict(row)

    async def add_message(
        self, session_id: str, role: str, text: str, pii_masked: bool = False
    ) -> None:
        row = MessageRow(
            session_id=session_id,
            role=role,
            text=text,
            pii_masked=1 if pii_masked else 0,
            created_at=_now(),
        )
        async with self.session() as session:
            session.add(row)
            await session.commit()

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        async with self.session() as session:
            rows = (
                await session.execute(
                    select(MessageRow).where(MessageRow.session_id == session_id)
                )
            ).scalars()
            return [
                {
                    "role": row.role,
                    "text": row.text,
                    "pii_masked": bool(row.pii_masked),
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    async def put_token(self, token: str, value_type: str, value: str) -> None:
        async with self.session() as session:
            existing = await session.get(VaultRow, token)
            if existing is not None:
                return
            session.add(
                VaultRow(
                    token=token,
                    type=value_type,
                    value=value,
                    created_at=_now(),
                )
            )
            await session.commit()

    async def get_token(self, token: str) -> dict[str, Any] | None:
        async with self.session() as session:
            row = await session.get(VaultRow, token)
            if row is None:
                return None
            return {"token": row.token, "type": row.type, "value": row.value}

    async def add_outbox(
        self,
        session_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        signature: str,
    ) -> None:
        row = OutboxRow(
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            signature=signature,
            status="queued",
            created_at=_now(),
        )
        async with self.session() as session:
            session.add(row)
            await session.commit()

    async def list_outbox(self, session_id: str | None = None) -> list[dict[str, Any]]:
        async with self.session() as session:
            stmt = select(OutboxRow).order_by(OutboxRow.id)
            if session_id:
                stmt = stmt.where(OutboxRow.session_id == session_id)
            rows = (await session.execute(stmt)).scalars()
            return [
                {
                    "event_type": row.event_type,
                    "payload": dict(row.payload),
                    "signature": row.signature,
                    "status": row.status,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    async def seed_kb_chunks(self, rows: list[dict[str, Any]]) -> int:
        async with self.session() as session:
            await session.execute(delete(KbChunkRow))
            session.add_all([KbChunkRow(**row) for row in rows])
            await session.commit()
        return len(rows)

    async def count_kb_chunks(self) -> int:
        async with self.session() as session:
            rows = (await session.execute(select(KbChunkRow))).scalars().all()
            return len(rows)
