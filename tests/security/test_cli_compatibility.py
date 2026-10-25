"""Exercise public CLI entrypoints, including real work and nonzero failures."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    return subprocess.run(  # noqa: S603 -- trusted interpreter, fixed local entrypoints, no shell
        [sys.executable, "-X", "utf8", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


@pytest.mark.parametrize(
    "script,arguments,expected",
    [
        ("static_verify", (), "static guard OK"),
        ("verify_contexts", (), "49 files"),
        ("verify_runtime_config_sync", (), "byte-identical"),
        ("verify_dependency_locks", (), "hashed exports verified"),
        ("export_knowledge_schemas", ("--verify",), "Knowledge schemas verified"),
        ("knowledge_smoke", ("--help",), "--output"),
        ("split_dataset", ("--help",), "--schema"),
        ("wheel_smoke", ("--help",), "wheel"),
    ],
)
def test_legacy_script_executes_entrypoint(script, arguments, expected) -> None:
    result = run_cli(f"scripts/{script}.py", *arguments)
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout


@pytest.mark.parametrize("job", ["build_index", "evaluate", "benchmark_semantic", "publish"])
def test_legacy_offline_module_forwards_arguments(job: str) -> None:
    module = f"smartevent_ai.tooling.knowledge.{job}"
    result = run_cli("-m", module, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    missing = run_cli("-m", module)
    assert missing.returncode != 0
    assert "required" in missing.stderr


@pytest.mark.parametrize(
    "entrypoint", [("scripts/source_manifest.py",), ("-m", "scripts.source_manifest")]
)
def test_manifest_compatibility_really_writes_and_rejects_drift(tmp_path, entrypoint) -> None:
    for name in (
        "scripts/__init__.py",
        "scripts/source_manifest.py",
        "scripts/verify/__init__.py",
        "scripts/verify/source_manifest.py",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (tmp_path / "README.md").write_text("reviewed source", encoding="utf-8")
    generated = run_cli(*entrypoint, cwd=tmp_path)
    assert generated.returncode == 0, generated.stderr
    assert (tmp_path / "MANIFEST_SHA256.json").is_file()
    verified = run_cli(*entrypoint, "--verify", cwd=tmp_path)
    assert verified.returncode == 0 and "verified" in verified.stdout
    (tmp_path / "README.md").write_text("unreviewed change", encoding="utf-8")
    rejected = run_cli(*entrypoint, "--verify", cwd=tmp_path)
    assert rejected.returncode != 0
    assert "mismatch" in rejected.stderr


def test_legacy_smoke_creates_evaluation_artifacts(tmp_path) -> None:
    import json

    output = tmp_path / "demo"
    result = run_cli("scripts/knowledge_smoke.py", "--output", str(output))
    assert result.returncode == 0, result.stderr
    evaluation = json.loads((output / "evaluation.json").read_bytes())
    assert evaluation["records"]
    assert evaluation["runtime_enable_authorized"] is False
    assert (output / "published/CURRENT.json").is_file()
