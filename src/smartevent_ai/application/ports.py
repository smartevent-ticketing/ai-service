"""Dependency-inversion ports implemented by outer adapters."""

from typing import Any, Protocol

from smartevent_ai.domain.dialogue import DialogueState, Understanding


class LanguageUnderstanding(Protocol):
    def parse(self, text: str, state: DialogueState) -> Understanding: ...


class BusinessReadTools(Protocol):
    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
