from __future__ import annotations

import json
import logging

import google.generativeai as genai
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None = None) -> None:
        s = get_settings()
        key = api_key or s.gemini_api_key
        if not key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=key)
        self._model = genai.GenerativeModel("gemini-2.0-flash")

    async def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        prompt = f"{system}\n\n{user}\n\nReturn JSON only matching keys in schema."
        # Gemini sync API in thread - simple fire in executor
        import asyncio

        loop = asyncio.get_event_loop()

        def _run():
            resp = self._model.generate_content(prompt)
            text = resp.text or ""
            return text

        text = await loop.run_in_executor(None, _run)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = json.loads(text[text.find("{") : text.rfind("}") + 1])
        # Map coaching_tips if model uses tips
        if "coaching_tips" not in obj and "tips" in obj:
            obj["coaching_tips"] = obj.pop("tips")
        return schema.model_validate(obj)
