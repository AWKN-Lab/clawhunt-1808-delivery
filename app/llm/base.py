"""LLM adapter interface + mock and OpenAI-compatible implementations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


class LLMTimeout(TimeoutError):
    """Raised when the model call exceeds the configured timeout."""


class LLMError(RuntimeError):
    """Raised when the model provider returns an error."""


@dataclass
class LLMRequest:
    system: str
    user_text: str
    context: dict[str, Any] = field(default_factory=dict)
    model: str = "mock-rule-engine"


@dataclass
class LLMResponse:
    text: str
    model: str


class LLMClient:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError


class MockLLM(LLMClient):
    """Deterministic mock: rule engine / templates / KB excerpt decide the draft.

    ``LLM_FAULT=timeout`` or ``error`` is injected here so the downgrade path
    can be tested without network access.
    """

    def __init__(self, fault: str = "none", delay_s: float = 0.0) -> None:
        self.fault = fault
        self.delay_s = delay_s

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fault == "timeout":
            raise LLMTimeout("mock timeout injected")
        if self.fault == "error":
            raise LLMError("mock provider error injected")
        draft = request.context.get("draft_text")
        if not draft:
            raise LLMError("mock requires context.draft_text")
        return LLMResponse(text=str(draft), model="mock-rule-engine")


class OpenAICompatibleLLM(LLMClient):
    """Real adapter (DeepSeek / any OpenAI-compatible endpoint).

    Requires ``LLM_MODE=openai``, ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL``.
    Never used by tests or eval (LLM_MODE=mock is enforced there).
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    async def complete(self, request: LLMRequest) -> LLMResponse:
        import httpx

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user_text},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMError(str(exc)) from exc
        if response.status_code >= 400:
            raise LLMError(f"provider status {response.status_code}")
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed provider response") from exc
        return LLMResponse(text=str(text), model=self.model)


def build_llm(settings) -> LLMClient:
    if settings.llm_mode == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_MODE=openai")
        return OpenAICompatibleLLM(
            settings.openai_base_url,
            settings.openai_api_key,
            settings.openai_model,
            timeout_s=settings.llm_timeout_s,
        )
    return MockLLM(fault=settings.llm_fault)
