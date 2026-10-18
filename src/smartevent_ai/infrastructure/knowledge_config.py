"""Reviewed RAG settings, trust anchors and default-disabled wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from smartevent_ai.domain.knowledge import KnowledgeError


class RagConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: Literal[1] = 1
    enabled: bool = False
    gate_id: Literal["RAG-APPROVED-CORPUS"] = "RAG-APPROVED-CORPUS"
    safety_gate_id: Literal["RAG-READONLY"] = "RAG-READONLY"
    catalog_path: str | None = None
    catalog_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    release_path: str | None = None
    release_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    max_catalog_age_seconds: int = Field(default=86400, ge=60, le=604800)
    max_catalog_bytes: int = Field(default=524288, ge=1024, le=1048576)
    max_release_bytes: int = Field(default=16000000, ge=1024, le=32000000)
    max_results: int = Field(default=3, ge=1, le=5)
    max_answer_chars: int = Field(default=6000, ge=256, le=16000)
    timeout_ms: int = Field(default=2000, ge=100, le=5000)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ReviewedRagConfig:
    """Re-read trusted files on each query: no stale gate/catalog permissions."""

    def __init__(self, config_dir: Path) -> None:
        self.root = config_dir.resolve()

    def load(self) -> RagConfig:
        path = self.root / "rag.yaml"
        if not path.exists():
            return RagConfig()
        try:
            if path.stat().st_size > 32768:
                raise KnowledgeError("Oversized RAG configuration")
            config = RagConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            if config.enabled:
                gates_path = self.root / "implementation_gates.yaml"
                if gates_path.stat().st_size > 65536:
                    raise KnowledgeError("Oversized gates")
                gates = yaml.safe_load(gates_path.read_text(encoding="utf-8"))["gates"]
                for key in (config.gate_id, config.safety_gate_id):
                    if gates.get(key, {}).get("status") != "PASS":
                        raise KnowledgeError("RAG integration gate is not PASS")
                if not all(
                    (
                        config.catalog_path,
                        config.catalog_sha256,
                        config.release_path,
                        config.release_sha256,
                    )
                ):
                    raise KnowledgeError("Enabled RAG requires pinned catalog and release")
            return config
        except (
            OSError,
            yaml.YAMLError,
            ValidationError,
            KeyError,
            TypeError,
            AttributeError,
        ) as exc:
            raise KnowledgeError("Invalid reviewed RAG configuration") from exc

    def resolve(self, path: str | None) -> Path:
        if path is None:
            raise KnowledgeError("Missing RAG artifact path")
        target = Path(path)
        return (self.root / target).resolve() if not target.is_absolute() else target.resolve()
