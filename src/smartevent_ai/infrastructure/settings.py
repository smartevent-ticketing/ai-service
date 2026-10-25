"""Runtime settings and deterministic configuration discovery."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_CONFIG_DIR = Path(__file__).resolve().parents[1] / "resources"


class Settings(BaseSettings):
    """Process-level settings.

    Business permissions are never toggled by environment booleans. A deployment
    may mount a reviewed config directory, but the files themselves must still
    satisfy the fail-closed registry/gate contracts.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    backend_base_url: str = "http://127.0.0.1:8080"
    config_dir: Path | None = Field(default=None)

    nlu_backend: str = "rule"
    nlu_adapter_path: Path | None = Field(default=None)
    nlu_base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    nlu_load_4bit: bool = True

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_nlu_model: str = "smartevent-nlu:1.5b"
    ollama_rag_model: str = "smartevent-rag:3b"
    ollama_timeout_seconds: float = 10.0

    rag_backend: str = "extractive"
    rag_adapter_path: Path | None = Field(default=None)
    rag_base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    rag_load_4bit: bool = True

    @property
    def effective_config_dir(self) -> Path:
        if self.config_dir is not None:
            return self.config_dir.expanduser().resolve()
        return _PACKAGE_CONFIG_DIR

    @property
    def registry_path(self) -> Path:
        return self.effective_config_dir / "runtime_tool_registry.yaml"

    @property
    def gates_path(self) -> Path:
        return self.effective_config_dir / "implementation_gates.yaml"
