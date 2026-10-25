"""Source distribution must not depend on ignored local evidence or secrets."""

import importlib.util
import json
import sys
from fnmatch import fnmatchcase
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


_SCRIPT_PACKAGES = ("verify", "knowledge", "release")


def load_script(name: str) -> ModuleType:
    candidates = [ROOT / "scripts" / package / f"{name}.py" for package in _SCRIPT_PACKAGES]
    candidates.append(ROOT / "scripts" / f"{name}.py")
    path = next((c for c in candidates if c.is_file()), None)
    assert path is not None, f"script not found: {name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_check_detects_hand_edited_resources_and_write_repairs(
    tmp_path: Path,
) -> None:
    module = load_script("sync_configs_to_resources")
    source = tmp_path / "configs"
    package = tmp_path / "resources"
    source.mkdir()
    package.mkdir()
    (source / "tool.yaml").write_bytes(b"enabled: false\n")
    (package / "tool.yaml").write_bytes(b"enabled: true\n")
    assert module.find_drift(source, package) != []
    with pytest.raises(SystemExit):
        module.main(["--check", "--source", str(source), "--package", str(package)])
    module.main(["--write", "--source", str(source), "--package", str(package)])
    assert module.find_drift(source, package) == []
    assert (package / "tool.yaml").read_bytes() == b"enabled: false\n"


def test_repeated_dependency_pins_stay_consistent() -> None:
    pins: dict[str, set[str]] = {}
    declared = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("tokenizers", "numpy", "onnxruntime"):
        versions = {
            line.split(f'"{name}==')[1].split('"')[0]
            for line in declared.splitlines()
            if f'"{name}==' in line
        }
        direct = (ROOT / "requirements/dev.txt").read_text(encoding="utf-8").splitlines()
        versions |= {line.split("==")[1].strip() for line in direct if line.startswith(f"{name}==")}
        assert versions, f"pin for {name} missing"
        pins[name] = versions
    for name, versions in pins.items():
        assert len(versions) == 1, f"conflicting pins for {name}: {sorted(versions)}"


def test_dev_txt_is_generated_from_dev_lock() -> None:
    module = load_script("export_dev_tools")
    rendered = module.render(
        (ROOT / "requirements/dev.lock").read_text(encoding="utf-8"),
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert rendered == (ROOT / "requirements/dev.txt").read_text(encoding="utf-8")


def test_verified_source_export_excludes_local_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_bytes(b"reviewed source\n")
    for filename in (
        ".env",
        ".env.secret",
        "local.log",
        "reports/private.md",
        ".venv/secret.txt",
        "__pycache__/local.pyc",
        "src/artifacts/index.json",
        "tests/.models/weights.bin",
    ):
        local = workspace / filename
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"LOCAL_SECRET")
    manifest = load_script("source_manifest")
    monkeypatch.setattr(manifest, "ROOT", workspace)
    monkeypatch.setattr(manifest, "MANIFEST", workspace / "MANIFEST_SHA256.json")
    monkeypatch.setitem(sys.modules, "source_manifest", manifest)
    manifest.write_manifest()
    expected = json.loads(manifest.MANIFEST.read_text(encoding="utf-8"))
    assert set(expected) == {"README.md"}
    exporter = load_script("export_source")
    output = tmp_path / "output"
    exporter.export_source(output)
    assert sorted(p.name for p in output.iterdir()) == ["MANIFEST_SHA256.json", "README.md"]
    assert (output / "README.md").read_bytes() == b"reviewed source\n"
    with pytest.raises(ValueError, match="new directory"):
        exporter.export_source(output)
    (workspace / "README.md").write_bytes(b"unreviewed edit\n")
    with pytest.raises(SystemExit, match="mismatch"):
        manifest.verify_manifest()


def test_ci_push_trigger_covers_current_development_branch_convention() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 resolver treats GitHub's "on" key as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    branch = "loop/p0-pr4-inplace-hardening"
    patterns = triggers["push"]["branches"]
    assert any(fnmatchcase(branch, pattern) for pattern in patterns)
