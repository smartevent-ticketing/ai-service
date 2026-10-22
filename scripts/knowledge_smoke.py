"""Source-checkout offline demo: TEST_ONLY chunking/retrieval/evaluation/publication."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from smartevent_ai.adapters.outbound.knowledge.contracts import canonical_json
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.domain.knowledge import ChunkingPolicy, KnowledgeError, digest
from smartevent_ai.tooling.offline_jobs.build_index import build_index
from smartevent_ai.tooling.offline_jobs.evaluate import evaluate
from smartevent_ai.tooling.offline_jobs.publish import publish

ROOT = Path(__file__).resolve().parents[1]


def demo(output: Path, now: datetime | None = None) -> dict[str, object]:
    if output.exists():
        raise KnowledgeError("Demo output must be a new directory")
    now = now or datetime.now(UTC).replace(microsecond=0)
    fixtures = ROOT / "tests/fixtures/rag"
    entries = []
    for name, source_id, title, audience in (
        ("refund.md", "TEST-REFUND", "Hoàn tiền TEST_ONLY", "customer_public"),
        ("guide.md", "TEST-GUIDE", "Hướng dẫn đặt vé TEST_ONLY", "customer_public"),
        ("staff.md", "TEST-STAFF", "Hoàn tiền nội bộ TEST_ONLY", "staff_internal"),
    ):
        entries.append(
            dict(
                path=name,
                metadata=dict(
                    source_id=source_id,
                    version="1.0.0",
                    title=title,
                    canonical_uri=f"approved://test/{source_id}",
                    content_sha256=digest((fixtures / name).read_bytes()),
                    status="approved",
                    audience=audience,
                    locale="vi-VN",
                    approved_at="2020-01-01T00:00:00+00:00",
                    effective_from="2020-01-02T00:00:00+00:00",
                    effective_until=None,
                    review_due_at="2035-01-01T00:00:00+00:00",
                    owner="TEST_ONLY_owner",
                    reviewer="TEST_ONLY_reviewer",
                    approval_id="TEST_ONLY_approval",
                ),
            )
        )
    catalog = canonical_json(
        dict(
            format_version=1,
            purpose="TEST_ONLY",
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(hours=12)).isoformat(),
            approval_ref="TEST_ONLY_no_policy_approval",
            sources=entries,
        )
    )
    output.mkdir(parents=True)
    catalog_path = output / "catalog.json"
    catalog_path.write_bytes(catalog)
    path = fixtures / "tokenizer.json"
    tokenizer = LocalTokenizer(
        path, digest(path.read_bytes()), "TEST_ONLY/byte-bpe-vi", "fixture-v1", 512
    )
    manifest = build_index(
        fixtures,
        catalog_path,
        digest(catalog),
        output / "build",
        StructureChunker(tokenizer, ChunkingPolicy(128, 16)),
        "TEST_ONLY_demo",
        now,
    )
    evaluation = evaluate(
        catalog_path,
        digest(catalog),
        output / "build/release.json",
        str(manifest["release_sha256"]),
        fixtures / "questions.jsonl",
        now,
    )
    (output / "evaluation.json").write_bytes(canonical_json(evaluation))
    pointer = publish(output / "build", output / "published")
    if any(
        evaluation["metrics"][split]["recall_at_5"] != 1.0  # type: ignore[index]
        or evaluation["metrics"][split]["negative_abstention_rate"] != 1.0  # type: ignore[index]
        for split in ("dev", "test")
    ):
        raise KnowledgeError("Synthetic smoke expectations failed; inspect evaluation.json")
    return dict(
        purpose="TEST_ONLY",
        runtime_enable_authorized=False,
        manifest=manifest,
        evaluation=evaluation,
        publication=pointer,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(demo(parser.parse_args().output), ensure_ascii=False, indent=2))
