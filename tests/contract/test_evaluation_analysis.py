"""P3 calibration analysis stays offline-only and fails closed on bad input."""

import json

import pytest

from smartevent_ai.domain.knowledge import KnowledgeError
from smartevent_ai.tooling.offline_jobs.analyze_evaluation import analyze


def _good_payload() -> dict:
    return {
        "records": [
            {
                "case_id": "a",
                "split": "dev",
                "query": "hoàn tiền?",
                "expected": ["TEST-REFUND@1.0.0"],
                "retrieved": ["TEST-REFUND@1.0.0"],
                "abstained": False,
                "latency_ms": 1.5,
            },
            {
                "case_id": "b",
                "split": "dev",
                "query": "thiên văn?",
                "expected": [],
                "retrieved": [],
                "abstained": True,
                "latency_ms": 2.5,
            },
        ]
    }


def test_analyze_reports_calibration_offline_only() -> None:
    result = analyze(_good_payload())
    assert result["evidence"] == "OFFLINE_ONLY"
    assert result["evaluation_ready"] is True
    assert result["dev"]["cases"] == 2
    assert result["metric_target"] == "exact_source_set_match"
    assert result["confidence_mode"] == "fixed_decision_proxy"
    assert result["dev"]["brier"] == 0.01
    assert result["dev"]["ece"] == 0.1
    assert result["dev"]["exact_source_set_accuracy"] == 1.0
    assert result["dev"]["latency_p50_ms"] == 2.0
    assert "enabled" not in json.dumps(result)


def test_analyze_malformed_input_is_not_ready() -> None:
    assert analyze({"records": []})["evaluation_ready"] is False
    assert analyze({"records": [{"case_id": "a"}]})["evaluation_ready"] is False
    dup = _good_payload()
    dup["records"].append(dict(dup["records"][0]))
    assert analyze(dup)["evaluation_ready"] is False


def test_analyze_rejects_non_object() -> None:
    with pytest.raises(KnowledgeError):
        analyze([])  # type: ignore[arg-type]


def test_analyze_never_touches_enablement() -> None:
    from pathlib import Path

    tree = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (Path("src/smartevent_ai/tooling/offline_jobs").resolve()).rglob("*.py")
    )
    assert 'enabled": true' not in tree and "enabled=True" not in tree


@pytest.mark.parametrize(
    "expected,retrieved,brier,accuracy",
    [
        (["A@1"], ["B@1"], 0.81, 0.0),
        (["A@1", "B@1"], ["A@1"], 0.81, 0.0),
        (["A@1"], ["A@1", "B@1"], 0.81, 0.0),
        (["A@1"], [], 0.81, 0.0),
        ([], ["A@1"], 0.81, 0.0),
        ([], [], 0.01, 1.0),
        (["A@1", "B@1"], ["B@1", "A@1"], 0.01, 1.0),
    ],
)
def test_decision_metric_compares_source_sets(expected, retrieved, brier, accuracy) -> None:
    row = dict(_good_payload()["records"][0])
    row.update(expected=expected, retrieved=retrieved, abstained=not retrieved)
    report = analyze({"records": [row]})
    assert report["dev"]["brier"] == brier
    assert report["dev"]["exact_source_set_accuracy"] == accuracy


@pytest.mark.parametrize(
    "changes",
    [
        {"case_id": []},
        {"case_id": True},
        {"case_id": " "},
        {"split": []},
        {"expected": [{}]},
        {"retrieved": [None]},
        {"expected": [" "]},
        {"retrieved": ["A@1", "A@1"]},
        {"abstained": "false"},
        {"abstained": True},
        {"latency_ms": "broken"},
        {"latency_ms": True},
        {"latency_ms": -1},
        {"latency_ms": float("nan")},
        {"latency_ms": float("inf")},
        {"latency_ms": 10**400},
        {"group": {}},
        {"group": " "},
        {"timed_out": 1},
    ],
)
def test_bad_record_cannot_produce_partial_metrics(changes) -> None:
    payload = _good_payload()
    payload["records"][0].update(changes)
    assert analyze(payload) == {"evidence": "OFFLINE_ONLY", "evaluation_ready": False}


def test_group_leakage_and_legacy_group_availability() -> None:
    payload = _good_payload()
    assert analyze(payload)["groups_verified"] is False
    payload["records"][0]["group"] = "same-policy"
    payload["records"][1].update(group="same-policy", split="test")
    assert analyze(payload)["evaluation_ready"] is False
    payload["records"][1]["group"] = "other-policy"
    assert analyze(payload)["groups_verified"] is True


def test_excessive_records_are_not_ready() -> None:
    assert analyze({"records": _good_payload()["records"] * 501})["evaluation_ready"] is False


def test_large_finite_latencies_keep_report_finite() -> None:
    import math

    payload = _good_payload()
    for row in payload["records"]:
        row["latency_ms"] = 1e308
    result = analyze(payload)
    assert result["evaluation_ready"] is True
    assert math.isfinite(result["dev"]["latency_p50_ms"])
