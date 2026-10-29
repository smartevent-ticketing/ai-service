"""Immutable knowledge values. No files, frameworks or model libraries."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit


class KnowledgeError(ValueError):
    """Unavailable or untrusted knowledge must never produce an answer."""


class SourceStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class Audience(StrEnum):
    PUBLIC = "customer_public"
    CUSTOMER = "customer_authenticated"
    STAFF = "staff_internal"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def fingerprint(value: object) -> str:
    return digest(canonical_json_bytes(value))


def require_hash(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise KnowledgeError("Expected lowercase SHA-256")


def require_time(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise KnowledgeError("Knowledge timestamps must include a timezone")


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_id: str
    version: str
    title: str
    canonical_uri: str
    content_sha256: str
    status: SourceStatus
    audience: Audience
    approved_at: datetime
    effective_from: datetime
    effective_until: datetime | None
    review_due_at: datetime
    owner: str
    reviewer: str
    approval_id: str
    locale: str = "vi-VN"

    def __post_init__(self) -> None:
        for value in (
            self.source_id,
            self.version,
            self.title,
            self.owner,
            self.reviewer,
            self.approval_id,
            self.canonical_uri,
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                raise KnowledgeError("Missing or excessive source metadata")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", self.source_id):
            raise KnowledgeError("Unsafe source ID")
        require_hash(self.content_sha256)
        try:
            uri = urlsplit(self.canonical_uri)
            _ = uri.port
        except ValueError as exc:
            raise KnowledgeError("Malformed canonical URI") from exc
        if (
            uri.scheme not in ("https", "approved")
            or not uri.netloc
            or uri.username
            or uri.password
            or uri.query
        ):
            raise KnowledgeError("Unsafe canonical URI")
        if not isinstance(self.status, SourceStatus) or not isinstance(self.audience, Audience):
            raise KnowledgeError("Untyped knowledge authority")
        if self.locale != "vi-VN":
            raise KnowledgeError("Unsupported locale")
        for timestamp in (self.approved_at, self.effective_from, self.review_due_at):
            require_time(timestamp)
        if self.effective_until is not None:
            require_time(self.effective_until)
            if self.effective_until <= self.effective_from:
                raise KnowledgeError("Empty effective interval")
        if self.approved_at > self.effective_from or self.review_due_at <= self.approved_at:
            raise KnowledgeError("Invalid approval/review chronology")

    def eligible(self, now: datetime) -> bool:
        require_time(now)
        return (
            self.status is SourceStatus.APPROVED
            and self.audience is Audience.PUBLIC
            and self.approved_at <= now
            and self.effective_from <= now < self.review_due_at
            and (self.effective_until is None or now < self.effective_until)
        )


@dataclass(frozen=True, slots=True)
class ChunkingPolicy:
    max_tokens: int = 384
    overlap_tokens: int = 64
    max_chunks: int = 2000
    algorithm: str = "structure-token-v1"

    def __post_init__(self) -> None:
        if (
            type(self.max_tokens) is not int
            or not 32 <= self.max_tokens <= 4096
            or type(self.overlap_tokens) is not int
            or not 0 <= self.overlap_tokens < self.max_tokens // 2
            or type(self.max_chunks) is not int
            or not 1 <= self.max_chunks <= 10000
            or self.algorithm != "structure-token-v1"
        ):
            raise KnowledgeError("Invalid chunking policy")


def check_budget(policy: ChunkingPolicy, context_window: int) -> None:
    if policy.max_tokens > context_window:
        raise KnowledgeError("Chunk budget exceeds embedding tokenizer context")


MAX_JSON_DEPTH = 24


def validate_json_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise KnowledgeError("Excessive JSON depth")
    if isinstance(value, dict):
        for child in value.values():
            validate_json_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            validate_json_depth(child, depth + 1)


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    source: SourceMetadata
    text: str


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    source_id: str
    source_version: str
    source_sha256: str
    normalized_sha256: str
    text: str
    context: str
    heading_path: tuple[str, ...]
    start: int
    end: int
    token_count: int
    profile_sha256: str
    parent_start: int
    parent_end: int

    def __post_init__(self) -> None:
        for value in (self.source_sha256, self.normalized_sha256, self.profile_sha256):
            require_hash(value)
        if (
            not self.text.strip()
            or len(self.text) > 100_000
            or len(self.context) > 10000
            or type(self.start) is not int
            or type(self.end) is not int
            or self.start < 0
            or type(self.parent_start) is not int
            or type(self.parent_end) is not int
            or self.end - self.start != len(self.text)
            or not 0 <= self.parent_start <= self.start < self.end <= self.parent_end
            or type(self.token_count) is not int
            or not 1 <= self.token_count <= 4096
            or not isinstance(self.heading_path, tuple)
            or any(not isinstance(v, str) or len(v) > 1000 for v in self.heading_path)
        ):
            raise KnowledgeError("Invalid chunk/provenance")

    @property
    def chunk_sha256(self) -> str:
        return digest(self.text.encode())

    @property
    def chunk_id(self) -> str:
        return fingerprint(
            [
                self.source_id,
                self.source_version,
                self.source_sha256,
                self.normalized_sha256,
                self.profile_sha256,
                self.context,
                self.heading_path,
                self.start,
                self.end,
                self.chunk_sha256,
                self.parent_start,
                self.parent_end,
            ]
        )


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    version: str
    title: str
    canonical_uri: str
    chunk_id: str
    heading_path: tuple[str, ...]
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class PolicyAnswer:
    answer: str
    citations: tuple[Citation, ...] = ()
    mode: str = "extractive"


@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    release_id: str
    sources: tuple[SourceMetadata, ...]
    chunks: tuple[KnowledgeChunk, ...]
    catalog_sha256: str
    documents: tuple[LoadedDocument, ...]


def eligible_chunks(snapshot: KnowledgeSnapshot, now: datetime) -> tuple[KnowledgeChunk, ...]:
    sources: dict[tuple[str, str, str], SourceMetadata] = {}
    lineages: set[str] = set()
    for source in snapshot.sources:
        if source.eligible(now):
            if source.source_id in lineages:
                raise KnowledgeError("Conflicting eligible source versions")
            lineages.add(source.source_id)
            sources[source.source_id, source.version, source.content_sha256] = source
    return tuple(
        c for c in snapshot.chunks if (c.source_id, c.source_version, c.source_sha256) in sources
    )
