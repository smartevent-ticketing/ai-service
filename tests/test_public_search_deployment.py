import importlib.util
import hashlib
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
        "backend_jar_sha256": "c" * 64,
        "proofs": {name: True for name in module.PROOFS},
        "business_http_trace": [{"method": "GET", "path": "/api/v1/events"}],
    }


@pytest.mark.parametrize(
    "broken",
    [
        "missing_snapshot",
        "changed_snapshot",
        "write",
        "stale",
        "missing_backend",
        "missing_filter_proof",
    ],
)
def test_incomplete_or_failed_evidence_cannot_enable_search(tmp_path: Path, broken: str) -> None:
    module = deployment_script()
    report = evidence(module)
    if broken == "missing_snapshot":
        report["database_snapshot_before"] = None
    elif broken == "changed_snapshot":
        report["database_snapshot_after"] = "b" * 64
    elif broken == "write":
        report["business_http_trace"] = [{"method": "POST", "path": "/api/v1/orders"}]
    elif broken == "stale":
        report["source_sha256"] = "b" * 64
    elif broken == "missing_backend":
        report.pop("backend_jar_sha256")
    else:
        report["proofs"].pop("price_lt_lte_and_inactive_child_test")
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


@pytest.mark.parametrize("change", [None, "backend", "permission", "policy", "source"])
def test_launcher_rejects_stale_or_tampered_deployments(tmp_path, monkeypatch, change) -> None:
    module = deployment_script()
    jar = tmp_path / "test-only.jar"
    jar.write_bytes(b"test-only backend artifact")
    monkeypatch.setattr(module, "BACKEND_JAR", jar)
    report = evidence(module)
    report["backend_jar_sha256"] = hashlib.sha256(jar.read_bytes()).hexdigest()
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    output = tmp_path / "deployment"
    module.prepare(path, output)
    if change == "backend":
        jar.write_bytes(b"different backend")
    elif change == "permission":
        registry = yaml.safe_load((output / "runtime_tool_registry.yaml").read_text())
        registry["tools"][1]["enabled"] = True
        (output / "runtime_tool_registry.yaml").write_text(yaml.safe_dump(registry))
    elif change == "policy":
        (output / "rag.yaml").write_text("enabled: true")
    elif change == "source":
        monkeypatch.setattr(module, "source_fingerprint", lambda: "d" * 64)
    if change:
        with pytest.raises(ValueError):
            module.validate_deployment(output)
    else:
        module.validate_deployment(output)
