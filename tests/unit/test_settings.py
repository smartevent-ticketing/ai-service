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


def test_nlu_settings_defaults_and_override(tmp_path: Path) -> None:
    defaults = Settings(_env_file=None)
    assert defaults.nlu_backend == "rule"
    assert defaults.nlu_adapter_path is None
    assert defaults.nlu_load_4bit is True

    custom = Settings(
        nlu_backend="peft",
        nlu_adapter_path=tmp_path / "adapter",
        nlu_base_model="Qwen/Qwen2.5-1.5B-Instruct",
        nlu_load_4bit=False,
        rag_backend="ollama",
        rag_adapter_path=tmp_path / "rag_adapter",
        _env_file=None,
    )
    assert custom.nlu_backend == "peft"
    assert custom.nlu_adapter_path == tmp_path / "adapter"
    assert custom.nlu_load_4bit is False
    assert custom.rag_backend == "ollama"
    assert custom.rag_adapter_path == tmp_path / "rag_adapter"


def test_bootstrap_builds_nlu_by_backend_setting() -> None:
    from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
    from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
    from smartevent_ai.infrastructure.bootstrap import build_chat

    # Rule backend
    chat_rule, _ = build_chat(Settings(nlu_backend="rule", _env_file=None))
    assert isinstance(chat_rule._nlu, RuleBasedVietnameseNLU)

    # Peft backend
    chat_peft, _ = build_chat(
        Settings(
            nlu_backend="peft",
            nlu_adapter_path=Path("models/unpacked_nlu_1.5b"),
            _env_file=None,
        )
    )
    assert isinstance(chat_peft._nlu, PeftTransformerNLU)

    # Ollama backend
    from smartevent_ai.adapters.outbound.ollama_nlu import OllamaNLU

    chat_ollama, _ = build_chat(
        Settings(
            nlu_backend="ollama",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_nlu_model="smartevent-nlu:1.5b",
            _env_file=None,
        )
    )
    assert isinstance(chat_ollama._nlu, OllamaNLU)

    # RAG backend generative wiring
    from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import OllamaPolicySynthesizer

    chat_rag_ollama, _ = build_chat(
        Settings(
            rag_backend="ollama",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_rag_model="smartevent-rag:3b",
            _env_file=None,
        )
    )
    assert isinstance(chat_rag_ollama._policies._synthesizer, OllamaPolicySynthesizer)
    assert chat_rag_ollama._policies.answer_mode == "generative"
