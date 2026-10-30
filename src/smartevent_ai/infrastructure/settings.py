"""Runtime settings and deterministic configuration discovery."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from typing import Literal
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

    nlu_backend: Literal["rule", "ollama", "peft"] = "rule"
    nlu_adapter_path: Path | None = Field(default=None)
    nlu_base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    nlu_load_4bit: bool = True
    nlu_preload: bool = False
    peft_sequential: bool = False
    nlu_timeout_seconds: float = Field(default=12.0, gt=0, le=600)
    rag_generation_timeout_seconds: float = Field(default=15.0, gt=0, le=600)

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_nlu_model: str = "smartevent-nlu:1.5b"
    ollama_rag_model: str = "smartevent-rag:3b"
    ollama_timeout_seconds: float = 10.0

    policy_backend: Literal["artifact", "http"] = "artifact"
    knowledge_base_url: str = "http://127.0.0.1:8010"
    knowledge_service_token: SecretStr = SecretStr("")
    rag_backend: Literal["extractive", "ollama", "peft"] = "extractive"
    rag_adapter_path: Path | None = Field(default=None)
    rag_base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    rag_load_4bit: bool = True

    @model_validator(mode="after")
    def sequential_requires_local_peft(self) -> "Settings":
        if self.peft_sequential and (
            self.nlu_backend != "peft"
            or self.rag_backend != "peft"
            or self.policy_backend != "artifact"
            or not self.nlu_load_4bit
            or not self.rag_load_4bit
        ):
            raise ValueError("Sequential demo requires local PEFT NLU/RAG with 4-bit loading")
        return self

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
