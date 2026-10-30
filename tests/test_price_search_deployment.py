import hashlib
import importlib
import json
from pathlib import Path

import pytest
import yaml

from conftest import ROOT


@pytest.mark.parametrize("broken", ["proof", "visibility", "write", "snapshot", None])
def test_price_release_requires_full_evidence_and_keeps_other_tools_disabled(
    tmp_path: Path, monkeypatch, broken
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    module = importlib.import_module("public_price_search_deployment")
    report = {
        "scope": "local-public-search-only",
        "feature": "public-price-search",
        "source_sha256": module.base.source_fingerprint(),
        "database_snapshot_before": "a" * 64,
        "database_snapshot_after": "a" * 64,
        "proofs": {p: True for p in (*module.base.PROOFS, *module.PRICE_PROOFS)},
        "business_http_trace": [{"method": "GET", "path": "/api/v1/events"}],
        "child_visibility_requests": module.expected_visibility_requests(),
        "price_fixture_sha256": hashlib.sha256(
            (ROOT / "tests/fixtures/public_price_search.sql").read_bytes()
        ).hexdigest(),
    }
    if broken == "proof":
        report["proofs"]["inactive_phase_visibility_test"] = False
    elif broken == "visibility":
        report["child_visibility_requests"][0]["status"] = 200
    elif broken == "write":
        report["child_visibility_requests"][0]["method"] = "POST"
    elif broken == "snapshot":
        report["database_snapshot_after"] = "b" * 64
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    output = tmp_path / "config"
    if broken:
        with pytest.raises(ValueError):
            module.prepare(path, output)
        assert not output.exists()
    else:
        module.prepare(path, output)
        registry = yaml.safe_load((output / "runtime_tool_registry.yaml").read_text())
        assert [t["name"] for t in registry["tools"] if t["enabled"]] == ["search_events"]
        gates = yaml.safe_load((output / "implementation_gates.yaml").read_text())
        assert gates["gates"]["PUBLISHED-CHILD"]["status"] == "PASS"
        assert gates["gates"]["PRIVATE-SELF-AUTH"]["status"] == "BLOCKED"
        assert (
            yaml.safe_load((ROOT / "configs/implementation_gates.yaml").read_text())["gates"][
                "PUBLISHED-CHILD"
            ]["status"]
            == "BLOCKED"
        )
