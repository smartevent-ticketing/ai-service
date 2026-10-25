"""Offline evaluation with explicit test-only results and frozen artifact hashes."""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field

from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.contracts import (
    WireModel,
    canonical_json,
    decode_json,
    read_bytes,
)
from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
from smartevent_ai.application.retrieve_policy import RetrievePolicy
from smartevent_ai.domain.knowledge import KnowledgeError, digest, require_time


class EvaluationCase(WireModel):
    case_id: str = Field(min_length=1, max_length=100)
    group: str = Field(min_length=1, max_length=100)
    split: Literal["dev", "test"]
    query: str = Field(min_length=1, max_length=2000)
    expected_sources: list[str] = Field(max_length=10)


class FrozenClock:
    def __init__(self, now: datetime) -> None:
        require_time(now)
        self._now = now

    def now(self) -> datetime:
        return self._now


class FrozenArtifacts:
    def __init__(
        self,
        catalog: bytes,
        catalog_hash: str,
        release: bytes,
        release_hash: str,
        max_age: int = 86400,
    ) -> None:
        self._values = catalog, catalog_hash, release, release_hash, max_age

    def artifacts(self) -> tuple[bytes, str, bytes, str, int]:
        return self._values


def evaluate(
    catalog: Path, catalog_hash: str, release: Path, release_hash: str, cases: Path, now: datetime
) -> dict[str, object]:
    raw_cases = read_bytes(cases, 2_000_000)
    rows = [
        EvaluationCase.model_validate(decode_json(line))
        for line in raw_cases.splitlines()
        if line.strip()
    ]
    if not rows or len(rows) > 1000 or len({r.case_id for r in rows}) != len(rows):
        raise KnowledgeError("Empty, excessive or duplicate evaluation cases")
    groups: dict[str, str] = {}
    for row in rows:
        if row.group in groups and groups[row.group] != row.split:
            raise KnowledgeError("Evaluation group leaks across dev/test")
        groups[row.group] = row.split
    source = FrozenArtifacts(
        read_bytes(catalog, 524288), catalog_hash, read_bytes(release, 16000000), release_hash
    )
    reader = RetrievePolicy(
        ArtifactKnowledgeStore(source, allow_test=True), BM25Retriever(), FrozenClock(now), limit=5
    )
    metrics: dict[str, object] = {}
    timeouts: dict[str, int] = {}
    records: list[dict[str, object]] = []
    for split in ("dev", "test"):
        positives = hits = reciprocal = ndcg = true_negative = negatives = 0.0
        durations: list[float] = []
        for row in (r for r in rows if r.split == split):
            started = perf_counter()
            answer = reader.answer(row.query)
            elapsed_ms = (perf_counter() - started) * 1000
            durations.append(elapsed_ms)
            if elapsed_ms > 2000:
                timeouts[row.case_id] = int(elapsed_ms)
            retrieved = list(dict.fromkeys(f"{c.source_id}@{c.version}" for c in answer.citations))
            expected = set(row.expected_sources)
            records.append(
                dict(
                    case_id=row.case_id,
                    group=row.group,
                    split=row.split,
                    query=row.query,
                    expected=sorted(expected),
                    retrieved=retrieved,
                    abstained=not retrieved,
                    latency_ms=elapsed_ms,
                    timed_out=elapsed_ms > 2000,
                )
            )
            if expected:
                positives += 1
                hits += len(expected.intersection(retrieved)) / len(expected)
                ranks = [i for i, v in enumerate(retrieved) if v in expected]
                reciprocal += 1 / (ranks[0] + 1) if ranks else 0
                ideal = sum(1 / math.log2(i + 2) for i in range(min(5, len(expected))))
                ndcg += sum(1 / math.log2(i + 2) for i in ranks) / ideal
            else:
                negatives += 1
                true_negative += not retrieved
        metrics[split] = dict(
            cases=len(durations),
            recall_at_5=hits / positives if positives else None,
            mrr_at_5=reciprocal / positives if positives else None,
            ndcg_at_5=ndcg / positives if positives else None,
            negative_abstention_rate=true_negative / negatives if negatives else None,
            latency_p50_ms=statistics.median(durations) if durations else None,
            latency_p95_ms=sorted(durations)[max(0, math.ceil(len(durations) * 0.95) - 1)]
            if durations
            else None,
        )
    return dict(
        format_version=1,
        evidence="OFFLINE_ONLY",
        runtime_enable_authorized=False,
        catalog_sha256=catalog_hash,
        release_sha256=release_hash,
        cases_sha256=digest(raw_cases),
        evaluated_at=now.isoformat(),
        python=platform.python_version(),
        platform=platform.platform(),
        metrics=metrics,
        timeouts_ms=timeouts,
        records=records,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("catalog", "release", "cases", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--catalog-sha256", required=True)
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--at", required=True, help="Explicit timezone-aware evaluation timestamp")
    args = parser.parse_args()
    result = evaluate(
        args.catalog,
        args.catalog_sha256,
        args.release,
        args.release_sha256,
        args.cases,
        datetime.fromisoformat(args.at),
    )
    if args.output.exists():
        raise KnowledgeError("Evaluation output must be new")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(result))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
