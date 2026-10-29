import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from conftest import ROOT


def deployment_script():
    spec = importlib.util.spec_from_file_location(
        "public_search_deployment", ROOT / "scripts/public_search_deployment.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(module) -> dict:
    return {
        "scope": "local-public-search-only",
        "source_sha256": module.source_fingerprint(),
        "database_snapshot_before": "a" * 64,
        "database_snapshot_after": "a" * 64,
        "proofs": {name: True for name in module.PROOFS},
        "business_http_trace": [{"method": "GET", "path": "/api/v1/events"}],
    }


@pytest.mark.parametrize("broken", ["missing_snapshot", "changed_snapshot", "write", "stale"])
def test_incomplete_or_failed_evidence_cannot_enable_search(tmp_path: Path, broken: str) -> None:
    module = deployment_script()
    report = evidence(module)
    if broken == "missing_snapshot":
        report["database_snapshot_before"] = None
    elif broken == "changed_snapshot":
        report["database_snapshot_after"] = "b" * 64
    elif broken == "write":
        report["business_http_trace"] = [{"method": "POST", "path": "/api/v1/orders"}]
    else:
        report["source_sha256"] = "b" * 64
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="evidence"):
        module.prepare(path, tmp_path / "deployment")
    assert not (tmp_path / "deployment").exists()


def test_scoped_deployment_preserves_default_disabled_configs(tmp_path: Path) -> None:
    module = deployment_script()
    before = module.source_fingerprint()
    path = tmp_path / "report.json"
    path.write_text(json.dumps(evidence(module)))
    output = tmp_path / "deployment"
    module.prepare(path, output)
    registry = yaml.safe_load((output / "runtime_tool_registry.yaml").read_text())
    assert [tool["name"] for tool in registry["tools"] if tool["enabled"]] == ["search_events"]
    assert module.source_fingerprint() == before
