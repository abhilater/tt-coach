from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        s = get_settings()
        key = api_key or s.openai_api_key
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = AsyncOpenAI(api_key=key)

    async def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        resp = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        text = resp.choices[0].message.content or "{}"
        obj = json.loads(text)
        return schema.model_validate(obj)
