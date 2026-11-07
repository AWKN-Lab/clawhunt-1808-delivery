"""Mock vault: tokenise raw PII, keep the raw value retrievable server-side."""
from __future__ import annotations

import hashlib

from app.errors import ApiError

PREFIX = {"phone": "PHONE_TOKEN", "id_card": "ID_TOKEN", "name": "NAME_TOKEN"}


class Vault:
    def __init__(self, db, audit=None) -> None:
        self.db = db
        self.audit = audit

    @staticmethod
    def make_token(value_type: str, value: str) -> str:
        digest = hashlib.sha256(f"{value_type}:{value}".encode("utf-8")).hexdigest()[:10]
        return f"{PREFIX[value_type]}_{digest}"

    async def tokenize(self, value_type: str, value: str) -> str:
        if value_type not in PREFIX:
            raise ApiError("invalid_vault_type", "type must be phone/id_card/name", 400)
        value = value.strip()
        if not value:
            raise ApiError("invalid_vault_value", "value must not be empty", 400)
        token = self.make_token(value_type, value)
        await self.db.put_token(token, value_type, value)
        return token

    async def resolve(self, token: str) -> tuple[str, str] | None:
        row = await self.db.get_token(token)
        if not row:
            return None
        return row["type"], row["value"]
