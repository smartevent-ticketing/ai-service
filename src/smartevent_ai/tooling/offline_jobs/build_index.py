"""Build deterministic knowledge artifacts using an explicitly pinned tokenizer."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from smartevent_ai.adapters.outbound.knowledge.contracts import (
    DocumentRecord,
    ReleaseRecord,
    SourceRecord,
    canonical_json,
    parse_catalog,
    read_bytes,
)
from smartevent_ai.adapters.outbound.knowledge.document_loader import LocalDocumentLoader
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.application.ingest_knowledge import IngestKnowledge
from smartevent_ai.domain.knowledge import ChunkingPolicy, KnowledgeError, digest, require_hash


def build_index(
    corpus_root: Path,
    catalog_path: Path,
    catalog_sha256: str,
    destination: Path,
    chunker: StructureChunker,
    source_revision: str,
    now: datetime | None = None,
) -> dict[str, object]:
    require_hash(catalog_sha256)
    if destination.exists() or not source_revision.strip():
        raise KnowledgeError("Use a new destination and an explicit source revision")
    raw = read_bytes(catalog_path, 524288)
    if digest(raw) != catalog_sha256:
        raise KnowledgeError("Catalog hash differs from approved input")
    catalog = parse_catalog(raw)
    clock = now or datetime.now(UTC)
    if catalog.purpose == "PRODUCTION":
        if (
            catalog.approval_ref.startswith("TEST_ONLY")
            or not catalog.issued_at <= clock < catalog.expires_at
            or any(not s.metadata.to_domain().eligible(clock) for s in catalog.sources)
        ):
            raise KnowledgeError("Production build requires current approved public sources")
    loader = LocalDocumentLoader(corpus_root)
    sources = tuple((s.path, s.metadata.to_domain()) for s in catalog.sources)
    chunks = IngestKnowledge(loader, chunker).build(sources)
    documents = [
        DocumentRecord(
            source=SourceRecord.model_validate(asdict(source)), text=loader.load(path, source).text
        )
        for path, source in sorted(sources, key=lambda s: (s[1].source_id, s[1].version))
    ]
    chunk_records = [
        {**asdict(c), "chunk_id": c.chunk_id, "chunk_sha256": c.chunk_sha256} for c in chunks
    ]
    release = ReleaseRecord.model_validate(
        dict(
            format_version=1,
            purpose=catalog.purpose,
            profile=chunker.profile,
            documents=documents,
            chunks=chunk_records,
            source_revision=source_revision,
        )
    )
    release_bytes = canonical_json(release.model_dump(mode="json"))
    chunk_bytes = b"".join(canonical_json(c) for c in chunk_records)
    manifest: dict[str, object] = dict(
        format_version=1,
        purpose=catalog.purpose,
        release_sha256=digest(release_bytes),
        chunks_sha256=digest(chunk_bytes),
        catalog_sha256=catalog_sha256,
        source_revision=source_revision,
        profile=chunker.profile,
        documents=len(documents),
        chunks=len(chunks),
        runtime_enable_authorized=False,
    )
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".knowledge-stage-", dir=destination.parent) as staging:
        staged = Path(staging) / "release"
        staged.mkdir()
        for name, data in (
            ("release.json", release_bytes),
            ("chunks.jsonl", chunk_bytes),
            ("BUILD_MANIFEST.json", canonical_json(manifest)),
        ):
            (staged / name).write_bytes(data)
        staged.rename(destination)  # New directory only: no partial publication/overwrite.
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--catalog-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--tokenizer-sha256", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--tokenizer-revision", required=True)
    parser.add_argument("--context-window", type=int, required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--max-tokens", type=int, default=384)
    parser.add_argument("--overlap-tokens", type=int, default=64)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    tokenizer = LocalTokenizer(
        args.tokenizer,
        args.tokenizer_sha256,
        args.tokenizer_model,
        args.tokenizer_revision,
        args.context_window,
        args.prefix,
    )
    chunker = StructureChunker(tokenizer, ChunkingPolicy(args.max_tokens, args.overlap_tokens))
    manifest = build_index(
        args.corpus_root,
        args.catalog,
        args.catalog_sha256,
        args.output,
        chunker,
        args.source_revision,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
