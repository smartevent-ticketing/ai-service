from pathlib import Path

from smartevent_ai.infrastructure.settings import Settings


def test_settings_default_to_packaged_configs_independent_of_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    fake = tmp_path / "configs"
    fake.mkdir()
    (fake / "runtime_tool_registry.yaml").write_text("malicious: true\n", encoding="utf-8")
    (fake / "implementation_gates.yaml").write_text("malicious: true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.registry_path.is_file()
    assert settings.gates_path.is_file()
    assert settings.registry_path.parent.name == "resources"


def test_explicit_config_dir_is_respected(tmp_path: Path) -> None:
    (tmp_path / "runtime_tool_registry.yaml").write_text("x: 1\n", encoding="utf-8")
    (tmp_path / "implementation_gates.yaml").write_text("x: 1\n", encoding="utf-8")
    settings = Settings(config_dir=tmp_path, _env_file=None)
    assert settings.registry_path == tmp_path / "runtime_tool_registry.yaml"
