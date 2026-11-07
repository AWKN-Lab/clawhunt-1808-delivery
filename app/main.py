"""FastAPI app for the rider recruitment agent (task 1/5)."""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.errors import ApiError
from app.models import (
    ErrorOut,
    MessageIn,
    MessageOut,
    SessionCreateIn,
    SessionCreateOut,
    VaultResolveOut,
    VaultTokenizeIn,
    VaultTokenizeOut,
)
from app.services import AgentService


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"([。！？\n])", text)
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        buffer += part
        if part and part in "。！？\n":
            chunks.append(buffer)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks or [text]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = AgentService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await service.start()
        app.state.service = service
        yield
        await service.close()

    app = FastAPI(
        title="骑手招聘 Agent 化信息收集平台 · 报名引擎",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        messages = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", []))
            messages.append(f"{location}: {item.get('msg')}")
        return JSONResponse(
            status_code=422,
            content=ErrorOut(
                code="invalid_request", message="; ".join(messages) or "invalid request"
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorOut(code=code, message=str(exc.detail)).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=ErrorOut(code="internal_error", message="internal server error").model_dump(),
        )

    # ------------------------------------------------------------------
    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return await service.health()

    @app.post("/api/v1/agent/sessions", status_code=201)
    async def create_session(body: SessionCreateIn) -> SessionCreateOut:
        consent_at = body.consent.accepted_at.isoformat()
        session_id = await service.create_session(
            body.source_channel, body.consent.version, consent_at
        )
        return SessionCreateOut(session_id=session_id)

    @app.post("/api/v1/agent/sessions/{session_id}/messages")
    async def post_message(session_id: str, body: MessageIn) -> MessageOut:
        result = await service.handle_message(session_id, body.text)
        return MessageOut(**result)

    @app.post("/api/v1/agent/sessions/{session_id}/messages/stream")
    async def stream_message(session_id: str, body: MessageIn) -> StreamingResponse:
        result = await service.handle_message(session_id, body.text)

        async def generator():
            yield _sse("meta", {"session_id": session_id})
            for sentence in split_sentences(result["reply"]):
                for char in sentence:
                    yield _sse("delta", {"text": char})
                    if settings.stream_delay_ms:
                        await asyncio.sleep(settings.stream_delay_ms / 1000)
            yield _sse("done", result)

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/agent/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        return await service.get_session(session_id)

    @app.post("/api/v1/vault/tokenize")
    async def vault_tokenize(body: VaultTokenizeIn) -> VaultTokenizeOut:
        token = await service.vault.tokenize(body.type, body.value)
        return VaultTokenizeOut(token=token)

    @app.get("/api/v1/vault/tokens/{token}")
    async def vault_resolve(token: str) -> VaultResolveOut:
        resolved = await service.vault.resolve(token)
        if resolved is None:
            raise ApiError("token_not_found", "token does not exist", 404)
        return VaultResolveOut(type=resolved[0], value=resolved[1])

    return app


app = create_app()
