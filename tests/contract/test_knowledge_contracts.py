from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from knowledge_helpers import NOW, catalog_bytes, source

from smartevent_ai.adapters.outbound.knowledge.contracts import (
    ChunkProfile,
    TokenizerProfile,
    canonical_json,
    decode_json,
    parse_catalog,
    read_bytes,
)
from smartevent_ai.domain.knowledge import (
    Audience,
    ChunkingPolicy,
    KnowledgeError,
    SourceStatus,
    fingerprint,
    require_hash,
)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_id": "../bad"},
        {"title": ""},
        {"content_sha256": "bad"},
        {"canonical_uri": "javascript:alert(1)"},
        {"canonical_uri": "https://["},
        {"canonical_uri": "https://example.com:invalid/policy"},
        {"canonical_uri": "https://user:secret@example.com/p"},
        {"canonical_uri": "https://example.com/p?token=secret"},
        {"locale": "en"},
        {"status": "approved"},
        {"audience": "customer_public"},
        {"approved_at": datetime(2020, 1, 1)},
        {"effective_until": datetime(2019, 1, 1)},
        {"review_due_at": datetime(2019, 1, 1)},
        {"approval_id": " "},
    ],
)
def test_source_metadata_rejects_unsafe_authority(changes) -> None:
    with pytest.raises(KnowledgeError):
        source(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": SourceStatus.DRAFT},
        {"status": SourceStatus.REVOKED},
        {"status": SourceStatus.SUPERSEDED},
        {"audience": Audience.STAFF},
        {"audience": Audience.CUSTOMER},
        {"effective_from": NOW + timedelta(days=1)},
        {"effective_until": NOW},
        {"review_due_at": NOW},
    ],
)
def test_eligibility_denies_unapproved_private_or_stale(changes) -> None:
    assert not source(**changes).eligible(NOW)


def test_exact_effective_boundaries() -> None:
    s = source(effective_from=NOW, effective_until=NOW + timedelta(seconds=1))
    assert s.eligible(NOW)
    assert not s.eligible(NOW + timedelta(seconds=1))
    assert not replace(s, effective_from=NOW + timedelta(microseconds=1)).eligible(NOW)


@pytest.mark.parametrize("values", [(True, 0), (31, 0), (4097, 0), (128, 64), (128, -1)])
def test_bad_chunking_budgets(values) -> None:
    with pytest.raises(KnowledgeError):
        ChunkingPolicy(*values)


@pytest.mark.parametrize(
    "payload",
    [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}', b"\xff", b"[[", b"[" * 30 + b"0" + b"]" * 30],
)
def test_strict_bounded_json(payload) -> None:
    with pytest.raises(KnowledgeError):
        decode_json(payload)


def test_catalog_requires_schema_and_no_duplicate_sources() -> None:
    assert len(parse_catalog(catalog_bytes()).sources) == 3
    with pytest.raises(KnowledgeError):
        parse_catalog(b'{"format_version":1}')
    with pytest.raises(KnowledgeError):
        parse_catalog(catalog_bytes(sources=[("refund.md", source()), ("refund.md", source())]))
    with pytest.raises(KnowledgeError):
        require_hash("F" * 64)


def test_bounded_artifact_io(tmp_path) -> None:
    with pytest.raises(KnowledgeError):
        read_bytes(tmp_path / "missing", 1)
    p = tmp_path / "huge"
    p.write_bytes(b"x" * 10)
    with pytest.raises(KnowledgeError):
        read_bytes(p, 9)


def _test_tokenizer_profile() -> TokenizerProfile:
    return TokenizerProfile(
        model_id="TEST_ONLY/byte-bpe-vi",
        revision="fixture-v1",
        sha256="0" * 64,
        prefix="",
        measurement="model_tokens",
        context_window=512,
    )


def test_chunk_profile_from_policy_round_trip_single_source() -> None:
    policy = ChunkingPolicy(384, 64)
    tokenizer = _test_tokenizer_profile()
    profile = ChunkProfile.from_policy(policy, "NFC_LF_v1", tokenizer)
    assert profile.max_tokens == 384
    assert profile.overlap_tokens == 64
    assert profile.max_chunks == 2000
    assert profile.algorithm == "structure-token-v1"
    assert profile.normalization == "NFC_LF_v1"
    expected = {
        "max_tokens": 384,
        "overlap_tokens": 64,
        "max_chunks": 2000,
        "algorithm": "structure-token-v1",
        "normalization": "NFC_LF_v1",
        "tokenizer": tokenizer.model_dump(mode="json"),
    }
    assert fingerprint(profile.model_dump(mode="json")) == fingerprint(expected)
    assert canonical_json(profile.model_dump(mode="json")).endswith(b"\n")


def test_chunk_profile_from_policy_rejects_out_of_bounds() -> None:
    with pytest.raises(KnowledgeError):
        ChunkingPolicy(128, 64)
    small_window = TokenizerProfile(
        model_id="TEST_ONLY/byte-bpe-vi",
        revision="fixture-v1",
        sha256="0" * 64,
        prefix="",
        measurement="model_tokens",
        context_window=64,
    )
    with pytest.raises(KnowledgeError):
        ChunkProfile.from_policy(ChunkingPolicy(384, 64), "NFC_LF_v1", small_window)
