"""Read-only knowledge composition. No ingestion or optional model import."""

import asyncio
from pathlib import Path
from smartevent_ai.application.knowledge_ports import PolicyReader

from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.contracts import read_bytes
from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
from smartevent_ai.application.knowledge_ports import PolicySynthesizer
from smartevent_ai.application.retrieve_policy import NO_EVIDENCE, RetrievePolicy
from smartevent_ai.domain.knowledge import KnowledgeError, PolicyAnswer, eligible_chunks
from smartevent_ai.infrastructure.knowledge_config import ReviewedRagConfig, SystemClock


class RuntimeArtifacts:
    def __init__(self, config: ReviewedRagConfig) -> None:
        self._config = config

    def artifacts(self) -> tuple[bytes, str, bytes, str, int]:
        config = self._config.load()
        if not config.enabled:
            raise KnowledgeError("Policy retrieval disabled")
        return (
            read_bytes(self._config.resolve(config.catalog_path), config.max_catalog_bytes),
            config.catalog_sha256 or "",
            read_bytes(self._config.resolve(config.release_path), config.max_release_bytes),
            config.release_sha256 or "",
            config.max_catalog_age_seconds,
        )


class RuntimePolicyReader:
    def __init__(
        self,
        config: ReviewedRagConfig,
        test_environment: bool = False,
        synthesizer: PolicySynthesizer | None = None,
    ) -> None:
        self._config = config
        self._store = ArtifactKnowledgeStore(RuntimeArtifacts(config), allow_test=test_environment)
        self._synthesizer = synthesizer

    @property
    def answer_mode(self) -> str:
        return "verified_extractive" if self._synthesizer is not None else "extractive"

    def status(self) -> str:
        try:
            if not self._config.load().enabled:
                return "disabled"
            now = SystemClock().now()
            snapshot = self._store.snapshot(now)
            return "ready" if eligible_chunks(snapshot, now) else "unavailable"
        except KnowledgeError:
            return "unavailable"

    async def answer(self, query: str) -> PolicyAnswer:
        try:
            config = self._config.load()
        except KnowledgeError:
            return PolicyAnswer(NO_EVIDENCE)
        if not config.enabled:
            return PolicyAnswer(NO_EVIDENCE)

        use_case = RetrievePolicy(
            self._store,
            BM25Retriever(),
            SystemClock(),
            config.max_results,
            config.max_answer_chars,
            synthesizer=self._synthesizer,
        )
        timeout_sec = 15.0 if self._synthesizer is not None else (config.timeout_ms / 1000)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(use_case.answer, query), timeout=timeout_sec
            )
        except TimeoutError:
            # When generative model times out, fallback to pure extractive answer without losing citations
            try:
                extractive_use_case = RetrievePolicy(
                    self._store,
                    BM25Retriever(),
                    SystemClock(),
                    config.max_results,
                    config.max_answer_chars,
                    synthesizer=None,
                )
                return extractive_use_case.answer(query)
            except Exception:
                return PolicyAnswer(NO_EVIDENCE)
        except KnowledgeError:
            return PolicyAnswer(NO_EVIDENCE)


class GateControlledPolicyReader:
    """Remote retrieval still requires reviewed AI-side RAG gates on every read."""

    def __init__(self, reader: PolicyReader, gates_path: Path) -> None:
        self._reader, self._gates_path = reader, gates_path

    @property
    def answer_mode(self) -> str:
        return getattr(self._reader, "answer_mode", "extractive")

    def _approved(self) -> bool:
        import yaml

        try:
            raw = read_bytes(self._gates_path, 32768)
            gates = yaml.safe_load(raw)["gates"]
            return all(
                gates[name]["status"] == "PASS" for name in ("RAG-APPROVED-CORPUS", "RAG-READONLY")
            )
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, KnowledgeError):
            return False

    def status(self) -> str:
        return self._reader.status() if self._approved() else "disabled"

    async def answer(self, query: str) -> PolicyAnswer:
        if not self._approved():
            return PolicyAnswer(NO_EVIDENCE)
        answer = await self._reader.answer(query)
        return answer if self._approved() else PolicyAnswer(NO_EVIDENCE)
