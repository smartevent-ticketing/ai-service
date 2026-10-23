"""Offline-only calibration analysis over evaluation JSONL records.

Reads an evaluation output (see evaluate.py ``records``), reports
calibration (ECE/Brier over abstention-as-confidence), and never touches
runtime configs, gates or enablement flags. Malformed input yields
``evaluation_ready=false`` instead of partial metrics.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from smartevent_ai.domain.knowledge import KnowledgeError


def _expected_keys(record: object) -> dict:
    if not isinstance(record, dict):
        raise KnowledgeError("Evaluation record must be an object")
    for key in ("case_id", "split", "expected", "retrieved", "abstained", "latency_ms"):
        if key not in record:
            raise KnowledgeError(f"Evaluation record missing field: {key}")
    if record["split"] not in ("dev", "test"):
        raise KnowledgeError("Evaluation record has unknown split")
    if not isinstance(record["expected"], list) or not isinstance(record["retrieved"], list):
        raise KnowledgeError("Evaluation record rankings must be lists")
    return record


def analyze(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise KnowledgeError("Evaluation payload must be an object")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
    try:
        rows = [_expected_keys(r) for r in records]
    except KnowledgeError:
        return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
    if len({r["case_id"] for r in rows}) != len(rows):
        return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
    seen_groups: dict[str, str] = {}
    for row in rows:
        group = str(row.get("group", row["case_id"]))
        if group in seen_groups and seen_groups[group] != row["split"]:
            return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
        seen_groups[group] = str(row["split"])
    report: dict[str, object] = {"evidence": "OFFLINE_ONLY", "evaluation_ready": True}
    for split in ("dev", "test"):
        selected = [r for r in rows if r["split"] == split]
        if not selected:
            report[split] = None
            continue
        correct = [1.0 if (bool(r["retrieved"]) == bool(r["expected"])) else 0.0 for r in selected]
        # Offline abstention-as-confidence: abstained cases carry low confidence
        # (0.1), answered cases high confidence (0.9). Brier/ECE then measure
        # whether abstention aligns with correctness; never used for enablement.
        confidence = [0.1 if r["abstained"] else 0.9 for r in selected]
        brier = sum((c - y) ** 2 for c, y in zip(confidence, correct, strict=True)) / len(selected)
        buckets: dict[int, list[float]] = {}
        for c, y in zip(confidence, correct, strict=True):
            buckets.setdefault(int(c * 10), []).append(y - c)
        ece = sum(abs(sum(v) / len(v)) * (len(v) / len(selected)) for v in buckets.values())
        latencies = sorted(float(r["latency_ms"]) for r in selected)
        report[split] = dict(
            cases=len(selected),
            brier=round(brier, 4),
            ece=round(ece, 4),
            latency_p50_ms=latencies[len(latencies) // 2],
            latency_p95_ms=latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)],
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_bytes().decode("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise KnowledgeError("Evaluation input unreadable") from exc
    result = analyze(payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
