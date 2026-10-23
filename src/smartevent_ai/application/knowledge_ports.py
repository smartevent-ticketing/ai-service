"""Ports separate knowledge orchestration from storage, parsing and tokenizers."""

from datetime import datetime
from typing import Any, Protocol

from smartevent_ai.domain.evidence import EvidenceVerdict
from smartevent_ai.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeSnapshot,
    LoadedDocument,
    PolicyAnswer,
    SourceMetadata,
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class DocumentLoader(Protocol):
    def load(self, relative_path: str, source: SourceMetadata) -> LoadedDocument: ...


class TokenCounter(Protocol):
    @property
    def profile(self) -> dict[str, Any]: ...

    def count(self, text: str) -> int: ...


class DocumentChunker(Protocol):
    @property
    def profile(self) -> dict[str, object]: ...

    def split(self, document: LoadedDocument) -> tuple[KnowledgeChunk, ...]: ...


class KnowledgeStore(Protocol):
    def snapshot(self, now: datetime) -> KnowledgeSnapshot: ...


class EvidenceRetriever(Protocol):
    def rank(
        self, query: str, chunks: tuple[KnowledgeChunk, ...], limit: int
    ) -> tuple[KnowledgeChunk, ...]: ...


class EvidenceJudge(Protocol):
    def judge(
        self, query: str, chunks: tuple[KnowledgeChunk, ...]
    ) -> tuple[tuple[KnowledgeChunk, EvidenceVerdict], ...]: ...


class PolicyReader(Protocol):
    async def answer(self, query: str) -> PolicyAnswer: ...

    def status(self) -> str: ...
