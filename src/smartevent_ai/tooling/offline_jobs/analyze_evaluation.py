"""Offline decision diagnostics with an explicit fixed confidence proxy.

The target is an exact match of expected and retrieved source sets, including
correct abstention. These are not calibrated model probabilities. Malformed
records yield evaluation_ready=false; no runtime gate/configuration is changed.
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
    if not isinstance(record["case_id"], str) or not record["case_id"].strip():
        raise KnowledgeError("Evaluation case ID must be non-empty text")
    if record["split"] not in ("dev", "test"):
        raise KnowledgeError("Evaluation record has unknown split")
    for key in ("expected", "retrieved"):
        ranking = record[key]
        if not isinstance(ranking, list) or any(
            not isinstance(source, str) or not source.strip() for source in ranking
        ):
            raise KnowledgeError("Evaluation rankings must contain non-empty source identifiers")
        if len(set(ranking)) != len(ranking):
            raise KnowledgeError("Duplicate evaluation source identifiers")
    if type(record["abstained"]) is not bool or record["abstained"] != (not record["retrieved"]):
        raise KnowledgeError("Abstention must agree with the retrieved sources")
    latency = record["latency_ms"]
    if type(latency) not in (int, float):
        raise KnowledgeError("Latency must be numeric")
    try:
        valid_latency = math.isfinite(latency) and latency >= 0
    except OverflowError as exc:
        raise KnowledgeError("Latency is outside numeric bounds") from exc
    if not valid_latency:
        raise KnowledgeError("Latency must be finite and nonnegative")
    if "group" in record and (not isinstance(record["group"], str) or not record["group"].strip()):
        raise KnowledgeError("Evaluation group must be non-empty text")
    if "timed_out" in record and type(record["timed_out"]) is not bool:
        raise KnowledgeError("Timeout flag must be boolean")
    return record


def analyze(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise KnowledgeError("Evaluation payload must be an object")
    records = payload.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= 1000:
        return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
    try:
        rows = [_expected_keys(r) for r in records]
    except KnowledgeError:
        return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
    if len({r["case_id"] for r in rows}) != len(rows):
        return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
    seen_groups: dict[str, str] = {}
    for row in rows:
        group = row.get("group", row["case_id"])
        if group in seen_groups and seen_groups[group] != row["split"]:
            return {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}
        seen_groups[group] = row["split"]
    report: dict[str, object] = {
        "evidence": "OFFLINE_ONLY",
        "evaluation_ready": True,
        "metric_target": "exact_source_set_match",
        "confidence_mode": "fixed_decision_proxy",
        "decision_confidence": 0.9,
        "groups_verified": all("group" in row for row in rows),
    }
    for split in ("dev", "test"):
        selected = [r for r in rows if r["split"] == split]
        if not selected:
            report[split] = None
            continue
        correct = [float(set(r["retrieved"]) == set(r["expected"])) for r in selected]
        # Confidence refers to the correctness of the selected decision, including
        # abstention. No model probabilities are available: this fixed proxy is
        # only a diagnostic and must never authorize runtime enablement.
        confidence = [0.9] * len(selected)
        brier = sum((c - y) ** 2 for c, y in zip(confidence, correct, strict=True)) / len(selected)
        buckets: dict[int, list[float]] = {}
        for c, y in zip(confidence, correct, strict=True):
            buckets.setdefault(int(c * 10), []).append(y - c)
        ece = sum(abs(sum(v) / len(v)) * (len(v) / len(selected)) for v in buckets.values())
        latencies = sorted(float(r["latency_ms"]) for r in selected)
        middle = len(latencies) // 2
        median = (
            latencies[middle]
            if len(latencies) % 2
            else latencies[middle - 1] / 2 + latencies[middle] / 2
        )
        report[split] = dict(
            cases=len(selected),
            exact_source_set_accuracy=sum(correct) / len(selected),
            brier=round(brier, 4),
            ece=round(ece, 4),
            latency_p50_ms=median,
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
