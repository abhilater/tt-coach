from __future__ import annotations

import json
import logging

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.ollama_base_url).rstrip("/")
        self.model = model or s.ollama_model

    async def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            text = data["message"]["content"]
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("ollama_json_parse_retry")
            obj = json.loads(text[text.find("{") : text.rfind("}") + 1])
        return schema.model_validate(obj)
