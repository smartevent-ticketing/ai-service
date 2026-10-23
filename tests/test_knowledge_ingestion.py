import json

import pytest
from knowledge_helpers import FIXTURES, NOW, catalog_bytes, make_bundle, source, tokenizer

from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.document_loader import LocalDocumentLoader
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.application.ingest_knowledge import IngestKnowledge
from smartevent_ai.domain.knowledge import KnowledgeError, digest
from smartevent_ai.tooling.offline_jobs import build_index as build_index_module
from smartevent_ai.tooling.offline_jobs.build_index import build_index
from smartevent_ai.tooling.offline_jobs.publish import publish


def test_build_is_byte_identical_and_published_pointer_is_atomic(tmp_path) -> None:
    catalog, output, manifest, artifacts = make_bundle(tmp_path)
    second = tmp_path / "second"
    chunker = StructureChunker(tokenizer())
    a = build_index(FIXTURES, catalog, digest(catalog.read_bytes()), second, chunker, "rev", NOW)
    third = tmp_path / "third"
    b = build_index(FIXTURES, catalog, digest(catalog.read_bytes()), third, chunker, "rev", NOW)
    assert a == b
    for name in ("release.json", "chunks.jsonl", "BUILD_MANIFEST.json"):
        assert (second / name).read_bytes() == (third / name).read_bytes()
    root = tmp_path / "published"
    pointer = publish(output, root)
    assert json.loads((root / "CURRENT.json").read_text()) == pointer
    assert publish(output, root) == pointer
    assert pointer["purpose"] == "TEST_ONLY"
    snapshot = ArtifactKnowledgeStore(artifacts, allow_test=True).snapshot(NOW)
    assert snapshot.chunks and len(snapshot.documents) == 3
    with pytest.raises(KnowledgeError):
        ArtifactKnowledgeStore(artifacts).snapshot(NOW)
    with pytest.raises(KnowledgeError):
        build_index(FIXTURES, catalog, manifest["catalog_sha256"], output, chunker, "rev", NOW)


def test_build_loads_each_source_exactly_once(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    raw = catalog_bytes()
    catalog.write_bytes(raw)
    calls: list[str] = []
    real_loader_cls = LocalDocumentLoader

    class CountingLoader(real_loader_cls):
        def load(self, relative_path, src):  # type: ignore[no-untyped-def]
            calls.append(relative_path)
            return super().load(relative_path, src)

    monkeypatch.setattr(build_index_module, "LocalDocumentLoader", CountingLoader)
    chunker = StructureChunker(tokenizer())
    build_index(FIXTURES, catalog, digest(raw), tmp_path / "out", chunker, "rev", NOW)
    assert sorted(calls) == ["guide.md", "refund.md", "staff.md"]


def test_build_rejects_hash_draft_empty_duplicate_and_caps(tmp_path) -> None:
    catalog = tmp_path / "catalog.json"
    raw = catalog_bytes()
    catalog.write_bytes(raw)
    chunker = StructureChunker(tokenizer())
    with pytest.raises(KnowledgeError):
        build_index(FIXTURES, catalog, "0" * 64, tmp_path / "out", chunker, "rev", NOW)
    draft = catalog_bytes(purpose="PRODUCTION")
    catalog.write_bytes(draft)
    with pytest.raises(KnowledgeError):
        build_index(FIXTURES, catalog, digest(draft), tmp_path / "out", chunker, "rev", NOW)
    ingest = IngestKnowledge(LocalDocumentLoader(FIXTURES), chunker)
    with pytest.raises(KnowledgeError):
        ingest.build(())
    with pytest.raises(KnowledgeError):
        ingest.build((("refund.md", source()), ("refund.md", source())))
    with pytest.raises(KnowledgeError):
        IngestKnowledge(LocalDocumentLoader(FIXTURES), chunker, 0).build((("refund.md", source()),))
