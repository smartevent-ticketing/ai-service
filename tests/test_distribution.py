"""Source distribution must not depend on ignored local evidence or secrets."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
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
