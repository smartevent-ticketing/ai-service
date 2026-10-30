"""Dependency-inversion ports implemented by outer adapters."""

from typing import Any, Protocol, runtime_checkable

from smartevent_ai.domain.dialogue import DialogueState, Understanding


class LanguageUnderstanding(Protocol):
    def parse(self, text: str, state: DialogueState) -> Understanding: ...


@runtime_checkable
class WarmableLanguageUnderstanding(Protocol):
    def warmup(self) -> Understanding: ...


class BusinessReadTools(Protocol):
    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ModelRuntime(Protocol):
    def status(self) -> dict[str, object]: ...

    def close(self) -> None: ...
