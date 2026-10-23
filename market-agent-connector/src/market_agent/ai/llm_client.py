"""OpenAI-compatible LLM client for trading analysis."""

from __future__ import annotations

import json
from typing import Any

import httpx


class LLMClient:
    """Calls any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=60.0)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(self, system: str, user: str, json_mode: bool = True) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def analyze_json(self, system: str, user: str) -> dict[str, Any]:
        raw = await self.chat(system, user, json_mode=True)
        return json.loads(raw)
