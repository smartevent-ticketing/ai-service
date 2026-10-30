import importlib.util
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def launcher(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/local"))
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    path = ROOT / "scripts/local/run_sequential.py"
    spec = importlib.util.spec_from_file_location("sequential_launcher", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("broken", [None, "stale", "expired", "failed", "partial", "extra_tool"])
def test_serving_rejects_incomplete_or_stale_corpus_evidence(tmp_path, monkeypatch, broken):
    module = launcher(monkeypatch)
    from build_local_help import CASES
    from public_search_deployment import source_fingerprint

    report = {
        "scope": "local-demo-help-only",
        "source_sha256": source_fingerprint(),
        "approval_sha256": sha256(
            (ROOT / "datasets/help_review_2026_10_30/approval.json").read_bytes()
        ).hexdigest(),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "cases": [{"passed": True} for _ in CASES],
        **{
            key: True
            for key in (
                "no_match",
                "revocation",
                "blocked_gate",
                "tampered_release",
                "expired_catalog",
                "http_routing",
                "private_queries_not_retrieved",
                "corpus_readonly",
            )
        },
    }
    if broken == "stale":
        report["source_sha256"] = "0" * 64
    elif broken == "expired":
        report["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    elif broken == "failed":
        report["http_routing"] = False
    elif broken == "partial":
        report["cases"] = []
    (tmp_path / "help_evidence.json").write_text(json.dumps(report), encoding="utf-8")
    registry = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text("utf-8"))
    if broken == "extra_tool":
        registry["tools"][1]["enabled"] = True
    (tmp_path / "runtime_tool_registry.yaml").write_text(yaml.safe_dump(registry), encoding="utf-8")
    if broken:
        with pytest.raises(ValueError):
            module.validate_demo_config(tmp_path)
    else:
        module.validate_demo_config(tmp_path)


def test_rag_missing_or_wrong_base_does_not_silently_download(monkeypatch, tmp_path):
    module = launcher(monkeypatch)
    (tmp_path / "config.json").write_text(json.dumps({"model_type": "qwen2", "hidden_size": 1536}))
    with pytest.raises(ValueError, match="does not match"):
        module.rag_paths(str(tmp_path))


def test_prepare_retry_preserves_existing_output_and_selects_only_verified_success(
    monkeypatch, tmp_path
):
    module = launcher(monkeypatch)
    import build_local_help

    prior = tmp_path / "help"
    prior.mkdir()
    (prior / "diagnostic.txt").write_text("failed attempt")
    pointer = tmp_path / "current.json"
    monkeypatch.setattr(module, "CURRENT_PROFILE", pointer)
    built = []

    def build(path):
        built.append(path)
        (path / "configs").mkdir(parents=True)

    monkeypatch.setattr(build_local_help, "build", build)
    monkeypatch.setattr(module, "validate_demo_config", lambda _: None)
    chosen = module.prepare_help(prior)
    assert chosen.parent != prior
    assert (prior / "diagnostic.txt").read_text() == "failed attempt"
    assert module.serving_config(None) == chosen
    assert module.serving_config(prior) == prior

    saved = pointer.read_bytes()

    def fail(_):
        raise AssertionError("failed acceptance")

    monkeypatch.setattr(build_local_help, "build", fail)
    with pytest.raises(AssertionError):
        module.prepare_help(prior)
    assert pointer.read_bytes() == saved
