import json
from dataclasses import replace
from datetime import timedelta

import pytest
from knowledge_helpers import NOW, make_bundle

from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.contracts import canonical_json
from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
from smartevent_ai.application.retrieve_policy import RetrievePolicy
from smartevent_ai.domain.knowledge import KnowledgeError, SourceStatus, digest
from smartevent_ai.tooling.offline_jobs.evaluate import FrozenArtifacts, FrozenClock, evaluate


class MemoryStore:
    def __init__(self, snapshot):
        self.value = snapshot

    def snapshot(self, now):
        return self.value


def test_retrieval_filters_before_rank_and_expands_complete_section(tmp_path) -> None:
    _, _, _, artifacts = make_bundle(tmp_path)
    snapshot = ArtifactKnowledgeStore(artifacts, True).snapshot(NOW)

    class RecordingBM25(BM25Retriever):
        def rank(self, query, chunks, limit):
            assert all(c.source_id != "TEST-STAFF" for c in chunks)
            return super().rank(query, chunks, limit)

    reader = RetrievePolicy(MemoryStore(snapshot), RecordingBM25(), FrozenClock(NOW))
    answer = reader.answer("chính sách hoàn tiền")
    assert answer.citations and "Ngoại lệ" in answer.answer
    assert "STAFF_SECRET" not in answer.answer
    assert (
        "phê duyệt của SmartEvent" in answer.answer
    )  # Exact disclaimer survives parent expansion.
    for citation in answer.citations:
        doc = next(d for d in snapshot.documents if d.source.source_id == citation.source_id)
        assert doc.text[citation.start : citation.end].strip() in answer.answer
    assert not reader.answer("thiên văn lượng tử").citations
    assert not reader.answer("tôi muốn hỏi").citations
    assert not BM25Retriever().rank("hoàn tiền", (), 3)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": SourceStatus.REVOKED},
        {"status": SourceStatus.DRAFT},
        {"status": SourceStatus.SUPERSEDED},
        {"effective_until": NOW},
        {"review_due_at": NOW},
    ],
)
def test_revocation_expiry_and_review_due_are_not_cached(tmp_path, changes) -> None:
    _, _, _, artifacts = make_bundle(tmp_path)
    snapshot = ArtifactKnowledgeStore(artifacts, True).snapshot(NOW)
    store = MemoryStore(snapshot)
    reader = RetrievePolicy(store, BM25Retriever(), FrozenClock(NOW))
    assert reader.answer("hoàn tiền").citations
    store.value = replace(
        snapshot,
        sources=tuple(
            replace(s, **changes) if s.source_id == "TEST-REFUND" else s for s in snapshot.sources
        ),
    )
    assert not reader.answer("hoàn tiền").citations


def test_authority_change_mid_request_and_forged_retriever_rejected(tmp_path) -> None:
    _, _, _, artifacts = make_bundle(tmp_path)
    snapshot = ArtifactKnowledgeStore(artifacts, True).snapshot(NOW)
    store = MemoryStore(snapshot)

    class RevokingRetriever(BM25Retriever):
        def rank(self, query, chunks, limit):
            store.value = replace(snapshot, catalog_sha256="0" * 64)
            return super().rank(query, chunks, limit)

    with pytest.raises(KnowledgeError):
        RetrievePolicy(store, RevokingRetriever(), FrozenClock(NOW)).answer("hoàn tiền")

    class ForgingRetriever:
        def rank(self, query, chunks, limit):
            return (next(c for c in snapshot.chunks if c.source_id == "TEST-STAFF"),)

    store.value = snapshot
    with pytest.raises(KnowledgeError):
        RetrievePolicy(store, ForgingRetriever(), FrozenClock(NOW)).answer("hoàn tiền")


def test_conflicting_versions_and_long_parent_abstain(tmp_path) -> None:
    _, _, _, artifacts = make_bundle(tmp_path)
    snapshot = ArtifactKnowledgeStore(artifacts, True).snapshot(NOW)
    store = MemoryStore(snapshot)
    with pytest.raises(KnowledgeError):
        RetrievePolicy(store, BM25Retriever(), FrozenClock(NOW), limit=0)
    for query in ("", "x" * 2001):
        with pytest.raises(KnowledgeError):
            RetrievePolicy(store, BM25Retriever(), FrozenClock(NOW)).answer(query)
    tiny = RetrievePolicy(store, BM25Retriever(), FrozenClock(NOW), max_answer_chars=256)
    assert not tiny.answer("hoàn tiền").citations
    refund = next(s for s in snapshot.sources if s.source_id == "TEST-REFUND")
    store.value = replace(snapshot, sources=snapshot.sources + (replace(refund, version="2.0"),))
    with pytest.raises(KnowledgeError):
        RetrievePolicy(store, BM25Retriever(), FrozenClock(NOW)).answer("hoàn tiền")


@pytest.mark.parametrize("change", ["stale", "future", "expired", "naive", "purpose", "promotion"])
def test_catalog_time_and_purpose_controls(tmp_path, change) -> None:
    _, _, _, artifacts = make_bundle(tmp_path)
    c, _, r, _, age = artifacts.artifacts()
    catalog, release = json.loads(c), json.loads(r)
    if change == "stale":
        catalog["issued_at"] = (NOW - timedelta(days=2)).isoformat()
    elif change == "future":
        catalog["issued_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == "expired":
        catalog["expires_at"] = NOW.isoformat()
    elif change == "naive":
        catalog["issued_at"] = NOW.replace(tzinfo=None).isoformat()
    elif change == "purpose":
        release["purpose"] = "PRODUCTION"
    else:
        catalog["purpose"] = release["purpose"] = "PRODUCTION"
        catalog["approval_ref"] = "reviewed"
    cb, rb = canonical_json(catalog), canonical_json(release)
    with pytest.raises(KnowledgeError):
        ArtifactKnowledgeStore(FrozenArtifacts(cb, digest(cb), rb, digest(rb), age), True).snapshot(
            NOW
        )


def test_evaluation_reports_real_metrics_and_prevents_query_group_leakage(tmp_path) -> None:
    catalog, output, manifest, _ = make_bundle(tmp_path)
    path = tmp_path / "cases.jsonl"
    rows = [
        dict(
            case_id="positive",
            group="refund",
            split="test",
            query="hoàn tiền",
            expected_sources=["TEST-REFUND@1.0.0"],
        ),
        dict(
            case_id="negative",
            group="astronomy",
            split="test",
            query="thiên văn lượng tử",
            expected_sources=[],
        ),
    ]
    path.write_bytes(b"".join(canonical_json(r) for r in rows))
    result = evaluate(
        catalog,
        manifest["catalog_sha256"],
        output / "release.json",
        manifest["release_sha256"],
        path,
        NOW,
    )
    assert result["runtime_enable_authorized"] is False
    assert result["metrics"]["test"]["recall_at_5"] == 1
    assert result["metrics"]["test"]["negative_abstention_rate"] == 1
    rows.append(dict(rows[0], case_id="leaking", split="dev"))
    path.write_bytes(b"".join(canonical_json(r) for r in rows))
    with pytest.raises(KnowledgeError):
        evaluate(
            catalog,
            manifest["catalog_sha256"],
            output / "release.json",
            manifest["release_sha256"],
            path,
            NOW,
        )
