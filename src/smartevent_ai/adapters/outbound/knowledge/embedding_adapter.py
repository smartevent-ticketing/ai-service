"""Explicit local ONNX mean-pooling embedding adapter for offline benchmarks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartevent_ai.adapters.outbound.knowledge.contracts import read_bytes
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.domain.knowledge import KnowledgeError, digest, require_hash


class LocalOnnxEmbeddings:
    def __init__(
        self,
        model: Path,
        sha256: str,
        model_id: str,
        revision: str,
        tokenizer: LocalTokenizer,
        dimension: int,
        document_prefix: str = "passage: ",
        query_prefix: str = "query: ",
    ) -> None:
        require_hash(sha256)
        if (
            not model_id.strip()
            or not revision.strip()
            or not 1 <= dimension <= 4096
            or len(document_prefix) > 100
            or len(query_prefix) > 100
        ):
            raise KnowledgeError("Embedding profile requires pinned identity and dimension")
        raw = read_bytes(model, 200_000_000)
        if digest(raw) != sha256:
            raise KnowledgeError("ONNX model checksum mismatch")
        try:
            import numpy as np
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self._session: Any = ort.InferenceSession(
                raw, sess_options=options, providers=["CPUExecutionProvider"]
            )
            self._np: Any = np
        except ImportError as exc:
            raise KnowledgeError("Install locked rag-semantic dependencies") from exc
        except Exception as exc:
            raise KnowledgeError("Cannot load pinned ONNX model") from exc
        self._tokenizer, self._dimension = tokenizer, dimension
        self._document_prefix, self._query_prefix = document_prefix, query_prefix
        self.profile: dict[str, Any] = dict(
            model_id=model_id,
            revision=revision,
            sha256=sha256,
            dimension=dimension,
            document_prefix=document_prefix,
            query_prefix=query_prefix,
            tokenizer=tokenizer.profile,
            pooling="attention_mask_mean",
            normalization="L2",
            provider="CPUExecutionProvider",
        )
        self._inputs = {i.name for i in self._session.get_inputs()}
        if not {"input_ids", "attention_mask"} <= self._inputs or self._inputs - {
            "input_ids",
            "attention_mask",
            "token_type_ids",
        }:
            raise KnowledgeError("Unsupported embedding input contract")

    def embed(self, text: str, query: bool = False) -> tuple[float, ...]:
        np = self._np
        ids = self._tokenizer.encode(text, self._query_prefix if query else self._document_prefix)
        tokens = np.asarray([ids], dtype=np.int64)
        feed = {"input_ids": tokens, "attention_mask": np.ones_like(tokens)}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(tokens)
        try:
            outputs = self._session.run(None, feed)
            hidden = outputs[0]
            if hidden.shape != (1, len(ids), self._dimension) or not np.isfinite(hidden).all():
                raise KnowledgeError("Embedding output shape/numbers invalid")
            mask = feed["attention_mask"][..., None]
            vector = (hidden * mask).sum(axis=1)[0] / mask.sum(axis=1)[0]
            norm = float(np.linalg.norm(vector))
            if not np.isfinite(norm) or norm <= 0:
                raise KnowledgeError("Embedding vector is zero or nonfinite")
            return tuple(float(v) for v in vector / norm)
        except KnowledgeError:
            raise
        except Exception as exc:
            raise KnowledgeError("Embedding inference failed") from exc
