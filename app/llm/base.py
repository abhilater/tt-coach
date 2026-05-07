from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        ...
