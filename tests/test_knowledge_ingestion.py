import json
from dataclasses import replace

import pytest
from knowledge_helpers import FIXTURES, NOW, catalog_bytes, make_bundle, source, tokenizer

from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.contracts import canonical_json
from smartevent_ai.adapters.outbound.knowledge.document_loader import LocalDocumentLoader
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.application.ingest_knowledge import IngestKnowledge
from smartevent_ai.domain.knowledge import KnowledgeError, digest
from smartevent_ai.tooling.knowledge.build_index import build_index
from smartevent_ai.tooling.knowledge.evaluate import FrozenArtifacts
from smartevent_ai.tooling.knowledge.publish import publish


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


@pytest.mark.parametrize(
    "mutation", ["duplicate", "chunk_hash", "profile", "text", "parent", "unknown_field"]
)
def test_release_tampering_fails_even_with_updated_outer_hash(tmp_path, mutation) -> None:
    _, output, _, artifacts = make_bundle(tmp_path)
    cat, ch, raw, _, age = artifacts.artifacts()
    data = json.loads(raw)
    if mutation == "duplicate":
        data["chunks"].append(data["chunks"][0])
    elif mutation == "chunk_hash":
        data["chunks"][0]["chunk_sha256"] = "0" * 64
    elif mutation == "profile":
        data["profile"]["max_tokens"] = 96
    elif mutation == "text":
        data["documents"][0]["text"] = "Modified source text"
    elif mutation == "parent":
        data["chunks"][0]["parent_end"] = 999999
    else:
        data["secret"] = "unexpected"
    changed = canonical_json(data)
    store = ArtifactKnowledgeStore(FrozenArtifacts(cat, ch, changed, digest(changed), age), True)
    with pytest.raises(KnowledgeError):
        store.snapshot(NOW)


def test_catalog_and_publication_corruption(tmp_path) -> None:
    _, output, _, artifacts = make_bundle(tmp_path)
    c, ch, r, rh, age = artifacts.artifacts()
    with pytest.raises(KnowledgeError):
        ArtifactKnowledgeStore(FrozenArtifacts(c, "0" * 64, r, rh), True).snapshot(NOW)
    data = json.loads(c)
    data["sources"][0]["metadata"]["title"] = "Different policy"
    changed = canonical_json(data)
    with pytest.raises(KnowledgeError):
        ArtifactKnowledgeStore(
            FrozenArtifacts(changed, digest(changed), r, rh, age), True
        ).snapshot(NOW)
    (output / "release.json").write_bytes(b"corrupted")
    with pytest.raises(KnowledgeError):
        publish(output, tmp_path / "pub")


def test_source_cannot_escape_root_using_symlink(tmp_path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("Outside root", encoding="utf-8")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    try:
        (corpus / "link.md").symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit test symlinks")
    with pytest.raises(KnowledgeError):
        LocalDocumentLoader(corpus).load(
            "link.md", replace(source(), content_sha256=digest(outside.read_bytes()))
        )
