"""Compare BM25, local dense and reciprocal-rank fusion on offline fixtures/corpora."""

from __future__ import annotations

import argparse
import json
import math
import platform
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.contracts import (
    canonical_json,
    decode_json,
    parse_release,
    read_bytes,
)
from smartevent_ai.adapters.outbound.knowledge.embedding_adapter import LocalOnnxEmbeddings
from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.domain.knowledge import KnowledgeError, digest, eligible_chunks, fingerprint
from smartevent_ai.tooling.knowledge.evaluate import EvaluationCase, FrozenArtifacts


class Embeddings(Protocol):
    def embed(self, text: str, query: bool = False) -> tuple[float, ...]: ...


def benchmark(
    artifacts: FrozenArtifacts, cases: Path, now: datetime, embedding: Embeddings
) -> dict[str, object]:
    snapshot = ArtifactKnowledgeStore(artifacts, allow_test=True).snapshot(now)
    chunks = eligible_chunks(snapshot, now)
    if not chunks:
        raise KnowledgeError("No eligible corpus to benchmark")
    raw_cases = read_bytes(cases, 2_000_000)
    rows = [
        EvaluationCase.model_validate(decode_json(line))
        for line in raw_cases.splitlines()
        if line.strip()
    ]
    if not rows or len(rows) > 1000 or len({r.case_id for r in rows}) != len(rows):
        raise KnowledgeError("Empty, excessive or duplicate benchmark cases")
    groups: dict[str, str] = {}
    for row in rows:
        if row.group in groups and groups[row.group] != row.split:
            raise KnowledgeError("Benchmark query group leakage")
        groups[row.group] = row.split
    started = perf_counter()
    cache: dict[str, tuple[float, ...]] = {}
    vectors = []
    for chunk in chunks:
        content = chunk.context + chunk.text
        key = digest(content.encode())
        if key not in cache:
            cache[key] = embedding.embed(content)
        vectors.append(cache[key])
    build_ms = (perf_counter() - started) * 1000
    dimension = len(vectors[0])
    if not dimension or any(
        len(v) != dimension or any(not math.isfinite(x) for x in v) for v in vectors
    ):
        raise KnowledgeError("Invalid benchmark vectors")
    results: list[dict[str, Any]] = []
    lexical = BM25Retriever()
    for row in rows:
        started = perf_counter()
        vector = embedding.embed(row.query, query=True)
        if len(vector) != dimension or any(not math.isfinite(v) for v in vector):
            raise KnowledgeError("Query vector incompatible with corpus")
        dense = sorted(
            range(len(chunks)),
            key=lambda i: (
                -sum(a * b for a, b in zip(vector, vectors[i], strict=True)),
                chunks[i].chunk_id,
            ),
        )[:5]
        sparse = lexical.rank(row.query, chunks, 5)
        sparse_ids = [c.chunk_id for c in sparse]
        dense_ids = [chunks[i].chunk_id for i in dense]
        combined: dict[str, float] = {}
        for ranking in (sparse_ids, dense_ids):
            for rank, chunk_id in enumerate(ranking):
                combined[chunk_id] = combined.get(chunk_id, 0.0) + 1 / (60 + rank + 1)
        hybrid_ids = sorted(combined, key=lambda k: (-combined[k], k))[:5]
        mapping = {c.chunk_id: f"{c.source_id}@{c.source_version}" for c in chunks}
        rankings = {
            name: list(dict.fromkeys(mapping[k] for k in ids))
            for name, ids in (
                ("bm25", sparse_ids),
                ("dense", dense_ids),
                ("hybrid_rrf", hybrid_ids),
            )
        }
        results.append(
            dict(
                case_id=row.case_id,
                split=row.split,
                expected=row.expected_sources,
                rankings=rankings,
                latency_ms=(perf_counter() - started) * 1000,
            )
        )
    metrics = {}
    for split in ("dev", "test"):
        selected = [r for r in results if r["split"] == split and r["expected"]]
        metrics[split] = {
            mode: sum(
                len(set(r["expected"]).intersection(r["rankings"][mode])) / len(set(r["expected"]))
                for r in selected
            )
            / len(selected)
            if selected
            else None
            for mode in ("bm25", "dense", "hybrid_rrf")
        }
    top1 = {}
    for split in ("dev", "test"):
        selected = [r for r in results if r["split"] == split and r["expected"]]
        top1[split] = {
            mode: sum(
                bool(r["rankings"][mode]) and r["rankings"][mode][0] in r["expected"]
                for r in selected
            )
            / len(selected)
            if selected
            else None
            for mode in ("bm25", "dense", "hybrid_rrf")
        }
    return dict(
        evidence="OFFLINE_RETRIEVAL_ONLY",
        runtime_enable_authorized=False,
        release_sha256=snapshot.release_id,
        cases_sha256=digest(raw_cases),
        embedding_build_ms=build_ms,
        vector_count=len(vectors),
        dimension=dimension,
        vector_payload_bytes=len(vectors) * dimension * 4,
        recall_at_5=metrics,
        source_hit_at_1=top1,
        results=results,
        python=platform.python_version(),
        dense_abstention_calibrated=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("catalog", "release", "cases", "tokenizer", "model", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "catalog-sha256",
        "release-sha256",
        "tokenizer-sha256",
        "model-sha256",
        "model-id",
        "revision",
        "at",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--dimension", type=int, required=True)
    parser.add_argument("--context-window", type=int, default=512)
    args = parser.parse_args()
    if args.output.exists():
        raise KnowledgeError("Benchmark output must be new")
    counter = LocalTokenizer(
        args.tokenizer,
        args.tokenizer_sha256,
        args.model_id,
        args.revision,
        args.context_window,
        "passage: ",
    )
    embedding = LocalOnnxEmbeddings(
        args.model, args.model_sha256, args.model_id, args.revision, counter, args.dimension
    )
    artifacts = FrozenArtifacts(
        read_bytes(args.catalog, 524288),
        args.catalog_sha256,
        read_bytes(args.release, 16000000),
        args.release_sha256,
    )
    release_profile = parse_release(artifacts.artifacts()[2]).profile.tokenizer
    if (
        release_profile.sha256 != args.tokenizer_sha256
        or release_profile.model_id != args.model_id
        or release_profile.revision != args.revision
        or release_profile.prefix != "passage: "
    ):
        raise KnowledgeError("Rebuild chunks with the selected embedding tokenizer/profile first")
    result = benchmark(artifacts, args.cases, datetime.fromisoformat(args.at), embedding)
    result["embedding_profile"] = embedding.profile
    result["embedding_profile_sha256"] = fingerprint(embedding.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(result))
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
