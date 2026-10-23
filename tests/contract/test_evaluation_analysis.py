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
    # Abstention-as-confidence: answered 0.9 vs correct, abstained 0.1 vs
    # correct -> ((0.1)^2 + (0.9)^2) / 2 = 0.41. Metric only, never enablement.
    assert result["dev"]["brier"] == 0.41
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
