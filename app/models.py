"""Pydantic contracts for the agent API (contract v1, task 1/5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["show_stations", "booking_confirmed", "handoff", "end_minor"]
JobType = Literal["fulltime", "parttime", "undecided"]
VaultType = Literal["phone", "id_card", "name"]


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=64)
    accepted_at: datetime


class SessionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_channel: str = Field(min_length=1, max_length=64)
    consent: ConsentIn


class SessionCreateOut(BaseModel):
    session_id: str


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


class Progress(BaseModel):
    done: int = Field(ge=0, le=7)
    total: int = 7
    fields: list[str]


class MessageOut(BaseModel):
    reply: str
    quick_replies: list[str]
    progress: Progress
    actions: list[Action]


class SessionGetOut(BaseModel):
    session_id: str
    status: str
    progress: Progress
    collected: dict[str, Any]
    candidate: dict[str, Any] | None
    ended_reason: str | None = None
    created_at: str


class VaultTokenizeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: VaultType
    value: str = Field(min_length=2, max_length=128)


class VaultTokenizeOut(BaseModel):
    token: str


class VaultResolveOut(BaseModel):
    type: str
    value: str


class ErrorOut(BaseModel):
    code: str
    message: str
