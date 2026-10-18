"""Explicit local tokenizer.json adapter. No model/network download at startup."""

from pathlib import Path
from typing import Any

from smartevent_ai.adapters.outbound.knowledge.contracts import read_bytes
from smartevent_ai.domain.knowledge import KnowledgeError, digest, require_hash


class LocalTokenizer:
    def __init__(
        self,
        path: Path,
        sha256: str,
        model_id: str,
        revision: str,
        context_window: int,
        prefix: str = "",
    ) -> None:
        require_hash(sha256)
        if (
            not model_id.strip()
            or not revision.strip()
            or revision.lower() in ("main", "master", "latest")
            or not 32 <= context_window <= 131072
        ):
            raise KnowledgeError("Tokenizer requires pinned identity and context window")
        data = read_bytes(path, 32_000_000)
        if digest(data) != sha256:
            raise KnowledgeError("Tokenizer checksum mismatch")
        try:
            from tokenizers import Tokenizer

            self._tokenizer: Any = Tokenizer.from_str(data.decode())
            self._tokenizer.no_truncation()
            self._tokenizer.no_padding()
        except ImportError as exc:
            raise KnowledgeError("Install the locked rag-ingest optional dependencies") from exc
        except Exception as exc:
            raise KnowledgeError("Invalid local tokenizer") from exc
        self._profile: dict[str, Any] = dict(
            model_id=model_id,
            revision=revision,
            sha256=sha256,
            prefix=prefix,
            measurement="model_tokens",
            context_window=context_window,
        )

    @property
    def profile(self) -> dict[str, Any]:
        return dict(self._profile)

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(self._profile["prefix"] + text).ids)

    def encode(self, text: str, prefix: str) -> list[int]:
        ids: list[int] = self._tokenizer.encode(prefix + text).ids
        if len(ids) > self._profile["context_window"]:
            raise KnowledgeError("Embedding input exceeds tokenizer context; no truncation allowed")
        return ids
