"""Read-only, bounded release reader. Catalog hashes are pinned by reviewed config."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Protocol

from smartevent_ai.adapters.outbound.knowledge.contracts import (
    ChunkProfile,
    parse_catalog,
    parse_release,
)
from smartevent_ai.adapters.outbound.knowledge.document_loader import validate_text
from smartevent_ai.domain.knowledge import (
    ChunkingPolicy,
    KnowledgeError,
    KnowledgeSnapshot,
    LoadedDocument,
    check_budget,
    digest,
    fingerprint,
    require_time,
)


class ArtifactConfiguration(Protocol):
    # The concrete configuration belongs to infrastructure; the adapter uses a
    # narrow structural protocol, avoiding an adapter -> composition-root import.
    def artifacts(self) -> tuple[bytes, str, bytes, str, int]: ...


class ArtifactKnowledgeStore:
    def __init__(self, configuration: ArtifactConfiguration, allow_test: bool = False) -> None:
        self._configuration, self._allow_test = configuration, allow_test

    def snapshot(self, now: datetime) -> KnowledgeSnapshot:
        require_time(now)
        catalog_bytes, catalog_hash, release_bytes, release_hash, max_age = (
            self._configuration.artifacts()
        )
        if digest(catalog_bytes) != catalog_hash or digest(release_bytes) != release_hash:
            raise KnowledgeError("Catalog/release does not match reviewed trust anchors")
        catalog, release = parse_catalog(catalog_bytes), parse_release(release_bytes)
        for value in (catalog.issued_at, catalog.expires_at):
            require_time(value)
        if not (
            catalog.issued_at <= now < catalog.expires_at
            and (now - catalog.issued_at).total_seconds() <= max_age
        ):
            raise KnowledgeError("Catalog expired, future-issued or stale")
        if catalog.purpose != release.purpose or (
            catalog.purpose == "TEST_ONLY" and not self._allow_test
        ):
            raise KnowledgeError("TEST_ONLY knowledge is forbidden outside explicit tests")
        if catalog.purpose == "PRODUCTION" and catalog.approval_ref.startswith("TEST_ONLY"):
            raise KnowledgeError("Synthetic approval cannot authorize production")
        if catalog.purpose == "PRODUCTION" and (
            release.profile.tokenizer.model_id.startswith("TEST_ONLY")
            or any(s.metadata.approval_id.startswith("TEST_ONLY") for s in catalog.sources)
        ):
            raise KnowledgeError("Synthetic fixtures cannot be promoted to production")
        policy = ChunkingPolicy(
            release.profile.max_tokens, release.profile.overlap_tokens, release.profile.max_chunks
        )
        check_budget(policy, release.profile.tokenizer.context_window)
        expected_profile = ChunkProfile.from_policy(
            policy, release.profile.normalization, release.profile.tokenizer
        )
        profile_hash = fingerprint(expected_profile.model_dump(mode="json"))
        current = {
            (s.metadata.source_id, s.metadata.version): s.metadata.to_domain()
            for s in catalog.sources
        }
        documents: list[LoadedDocument] = []
        lookup: dict[tuple[str, str, str], LoadedDocument] = {}
        for record in release.documents:
            source = record.source.to_domain()
            key = source.source_id, source.version, source.content_sha256
            if key in lookup:
                raise KnowledgeError("Duplicate release document")
            live = current.get((source.source_id, source.version))
            if live is not None and replace(source, status=live.status) != live:
                raise KnowledgeError("Source authority differs from release")
            validate_text(record.text)
            loaded = LoadedDocument(source, record.text)
            lookup[key] = loaded
            documents.append(loaded)
        chunks = tuple(c.to_domain() for c in release.chunks)
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise KnowledgeError("Duplicate release chunks")
        counts: dict[tuple[str, str], int] = {}
        for chunk in chunks:
            document = lookup.get((chunk.source_id, chunk.source_version, chunk.source_sha256))
            if (
                document is None
                or chunk.normalized_sha256 != digest(document.text.encode())
                or chunk.text != document.text[chunk.start : chunk.end]
                or chunk.parent_end > len(document.text)
                or chunk.token_count > policy.max_tokens
                or chunk.profile_sha256 != profile_hash
            ):
                raise KnowledgeError("Broken release provenance/budget")
            key2 = chunk.source_id, chunk.source_version
            counts[key2] = counts.get(key2, 0) + 1
            if counts[key2] > policy.max_chunks:
                raise KnowledgeError("Release exceeds per-source chunk cap")
        return KnowledgeSnapshot(
            release_hash, tuple(current.values()), chunks, catalog_hash, tuple(documents)
        )
