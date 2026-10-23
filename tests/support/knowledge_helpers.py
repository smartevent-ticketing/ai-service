"""Explicit TEST_ONLY catalogs; these fixtures never constitute policy approval."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from smartevent_ai.adapters.outbound.knowledge.contracts import SourceRecord, canonical_json
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.domain.knowledge import (
    Audience,
    ChunkingPolicy,
    SourceMetadata,
    SourceStatus,
    digest,
)
from smartevent_ai.infrastructure.knowledge_config import RagConfig
from smartevent_ai.tooling.offline_jobs.build_index import build_index
from smartevent_ai.tooling.offline_jobs.evaluate import FrozenArtifacts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/rag"
NOW = datetime.now(UTC).replace(microsecond=0)


def source(**changes) -> SourceMetadata:
    values = dict(
        source_id="TEST-REFUND",
        version="1.0.0",
        title="Hoàn tiền TEST_ONLY",
        canonical_uri="approved://test/refund",
        content_sha256=digest((FIXTURES / "refund.md").read_bytes()),
        status=SourceStatus.APPROVED,
        audience=Audience.PUBLIC,
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        effective_from=datetime(2020, 1, 2, tzinfo=UTC),
        effective_until=None,
        review_due_at=datetime(2035, 1, 1, tzinfo=UTC),
        owner="TEST_ONLY_owner",
        reviewer="TEST_ONLY_reviewer",
        approval_id="TEST_ONLY_approval",
    )
    values.update(changes)
    return SourceMetadata(**values)


def tokenizer() -> LocalTokenizer:
    path = FIXTURES / "tokenizer.json"
    return LocalTokenizer(
        path, digest(path.read_bytes()), "TEST_ONLY/byte-bpe-vi", "fixture-v1", 512
    )


def catalog_bytes(sources=None, **changes) -> bytes:
    if sources is None:
        sources = [
            ("refund.md", source()),
            (
                "guide.md",
                source(
                    source_id="TEST-GUIDE",
                    title="Hướng dẫn đặt vé TEST_ONLY",
                    canonical_uri="approved://test/guide",
                    content_sha256=digest((FIXTURES / "guide.md").read_bytes()),
                ),
            ),
            (
                "staff.md",
                source(
                    source_id="TEST-STAFF",
                    title="Hoàn tiền staff TEST_ONLY",
                    audience=Audience.STAFF,
                    canonical_uri="approved://test/staff",
                    content_sha256=digest((FIXTURES / "staff.md").read_bytes()),
                ),
            ),
        ]
    values = dict(
        format_version=1,
        purpose="TEST_ONLY",
        issued_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(hours=12)).isoformat(),
        approval_ref="TEST_ONLY_not_an_approval",
        sources=[
            dict(path=path, metadata=SourceRecord.model_validate(asdict(s)).model_dump(mode="json"))
            for path, s in sources
        ],
    )
    values.update(changes)
    return canonical_json(values)


def make_bundle(tmp_path: Path, max_tokens=128, overlap=16):
    tmp_path.mkdir(parents=True, exist_ok=True)
    catalog = tmp_path / "catalog.json"
    raw = catalog_bytes()
    catalog.write_bytes(raw)
    output = tmp_path / "build"
    chunker = StructureChunker(tokenizer(), ChunkingPolicy(max_tokens, overlap))
    manifest = build_index(
        FIXTURES, catalog, digest(raw), output, chunker, "TEST_ONLY_revision", NOW
    )
    frozen = FrozenArtifacts(
        raw, digest(raw), (output / "release.json").read_bytes(), str(manifest["release_sha256"])
    )
    return catalog, output, manifest, frozen


def configure(tmp_path: Path, catalog: Path, output: Path, manifest):
    root = tmp_path / "config"
    root.mkdir(exist_ok=True)
    repository = Path(__file__).resolve().parents[2]
    for name in ("runtime_tool_registry.yaml", "implementation_gates.yaml"):
        (root / name).write_bytes((repository / "configs" / name).read_bytes())
    gates = yaml.safe_load((root / "implementation_gates.yaml").read_text())
    for gate in ("RAG-APPROVED-CORPUS", "RAG-READONLY"):
        gates["gates"][gate]["status"] = "PASS"
    (root / "implementation_gates.yaml").write_text(yaml.safe_dump(gates), encoding="utf-8")
    config = RagConfig(
        enabled=True,
        catalog_path=str(catalog),
        catalog_sha256=str(manifest["catalog_sha256"]),
        release_path=str(output / "release.json"),
        release_sha256=str(manifest["release_sha256"]),
    )
    (root / "rag.yaml").write_text(yaml.safe_dump(config.model_dump()), encoding="utf-8")
    return root
