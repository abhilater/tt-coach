from __future__ import annotations

import logging

from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


def build_provider(kind: str) -> LLMProvider:
    k = kind.strip().lower()
    if k == "ollama":
        return OllamaProvider()
    if k == "gemini":
        return GeminiProvider()
    if k == "openai":
        return OpenAIProvider()
    raise ValueError(f"unknown_llm_provider:{kind}")


async def complete_for_task(task: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    s = get_settings()
    key = {
        "summary": s.llm_summary,
        "insights": s.llm_insights,
        "tagging": s.llm_tagging,
    }.get(task, s.llm_insights)
    try:
        provider = build_provider(key)
        return await provider.complete_json(system, user, schema)
    except Exception as e:
        logger.warning("llm_fallback task=%s err=%s", task, type(e).__name__)
        # Fallback chain: ollama -> gemini -> openai if configured
        for fb in ("ollama", "gemini", "openai"):
            if fb == key:
                continue
            try:
                p = build_provider(fb)
                return await p.complete_json(system, user, schema)
            except Exception:
                continue
        raise
