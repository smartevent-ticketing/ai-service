"""Strict artifact wire contracts and bounded JSON IO at the outer boundary."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from smartevent_ai.domain.knowledge import (
    Audience,
    KnowledgeChunk,
    KnowledgeError,
    SourceMetadata,
    SourceStatus,
    require_time,
)


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("format_version", mode="before", check_fields=False)
    @classmethod
    def strict_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Format version must be an integer")
        return value


class SourceRecord(WireModel):
    source_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    version: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    canonical_uri: str = Field(min_length=1, max_length=1024)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: SourceStatus
    audience: Audience
    approved_at: datetime
    effective_from: datetime
    effective_until: datetime | None
    review_due_at: datetime
    owner: str = Field(min_length=1, max_length=100)
    reviewer: str = Field(min_length=1, max_length=100)
    approval_id: str = Field(min_length=1, max_length=100)
    locale: Literal["vi-VN"] = "vi-VN"

    @field_validator(
        "approved_at", "effective_from", "effective_until", "review_due_at", mode="before"
    )
    @classmethod
    def explicit_timestamp(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("Expected explicit date-time, not numeric timestamp")
        return value

    def to_domain(self) -> SourceMetadata:
        return SourceMetadata(**self.model_dump())


class CatalogSource(WireModel):
    path: str = Field(min_length=1, max_length=512)
    metadata: SourceRecord


class CatalogRecord(WireModel):
    format_version: Literal[1]
    purpose: Literal["TEST_ONLY", "PRODUCTION"]
    issued_at: datetime
    expires_at: datetime
    approval_ref: str = Field(min_length=1, max_length=512)
    sources: list[CatalogSource] = Field(min_length=1, max_length=1000)

    @field_validator("issued_at", "expires_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: Any) -> Any:
        if not isinstance(value, (str, datetime)):
            raise ValueError("Expected explicit date-time")
        return value


class ChunkRecord(WireModel):
    source_id: str
    source_version: str
    source_sha256: str
    normalized_sha256: str
    text: str = Field(min_length=1, max_length=100000)
    context: str = Field(max_length=10000)
    heading_path: list[str] = Field(max_length=6)
    start: int = Field(strict=True, ge=0)
    end: int = Field(strict=True, ge=1)
    token_count: int = Field(strict=True, ge=1, le=4096)
    profile_sha256: str
    parent_start: int = Field(strict=True, ge=0)
    parent_end: int = Field(strict=True, ge=1)
    chunk_id: str
    chunk_sha256: str

    def to_domain(self) -> KnowledgeChunk:
        data = self.model_dump(exclude={"chunk_id", "chunk_sha256"})
        data["heading_path"] = tuple(data["heading_path"])
        chunk = KnowledgeChunk(**data)
        if chunk.chunk_id != self.chunk_id or chunk.chunk_sha256 != self.chunk_sha256:
            raise KnowledgeError("Chunk integrity failed")
        return chunk


class TokenizerProfile(WireModel):
    model_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prefix: str = Field(max_length=100)
    measurement: Literal["model_tokens"]
    context_window: int = Field(strict=True, ge=32, le=131072)


class ChunkProfile(WireModel):
    algorithm: Literal["structure-token-v1"]
    normalization: Literal["NFC_LF_v1"]
    max_tokens: int = Field(strict=True, ge=32, le=4096)
    overlap_tokens: int = Field(strict=True, ge=0, le=2047)
    max_chunks: int = Field(strict=True, ge=1, le=10000)
    tokenizer: TokenizerProfile


class DocumentRecord(WireModel):
    source: SourceRecord
    text: str = Field(min_length=1, max_length=1000000)


class ReleaseRecord(WireModel):
    format_version: Literal[1]
    purpose: Literal["TEST_ONLY", "PRODUCTION"]
    profile: ChunkProfile
    documents: list[DocumentRecord] = Field(min_length=1, max_length=1000)
    chunks: list[ChunkRecord] = Field(min_length=1, max_length=10000)
    source_revision: str = Field(min_length=1, max_length=100)


def read_bytes(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as exc:
        raise KnowledgeError("Knowledge artifact unavailable") from exc
    if len(data) > limit:
        raise KnowledgeError("Knowledge artifact exceeds byte limit")
    return data


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise KnowledgeError("Duplicate JSON keys")
        result[key] = value
    return result


def decode_json(data: bytes) -> Any:
    try:
        value = json.loads(
            data,
            object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(KnowledgeError("Nonfinite JSON")),
        )

        def check(item: Any, depth: int) -> None:
            if depth > 24:
                raise KnowledgeError("Excessive JSON depth")
            if isinstance(item, dict):
                for v in item.values():
                    check(v, depth + 1)
            elif isinstance(item, list):
                for v in item:
                    check(v, depth + 1)
            elif isinstance(item, float) and not math.isfinite(item):
                raise KnowledgeError("Nonfinite JSON")

        check(value, 0)
        return value
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise KnowledgeError("Invalid knowledge JSON") from exc


def parse_catalog(data: bytes) -> CatalogRecord:
    try:
        record = CatalogRecord.model_validate(decode_json(data))
        require_time(record.issued_at)
        require_time(record.expires_at)
        if record.expires_at <= record.issued_at:
            raise KnowledgeError("Invalid catalog validity interval")
        for source in record.sources:
            source.metadata.to_domain()
        identities = [(s.metadata.source_id, s.metadata.version) for s in record.sources]
        if len(set(identities)) != len(identities):
            raise KnowledgeError("Duplicate catalog source/version")
        return record
    except ValidationError as exc:
        raise KnowledgeError("Invalid knowledge catalog schema") from exc


def parse_release(data: bytes) -> ReleaseRecord:
    try:
        return ReleaseRecord.model_validate(decode_json(data))
    except ValidationError as exc:
        raise KnowledgeError("Invalid knowledge release schema") from exc


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
