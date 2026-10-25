"""Read-only knowledge composition. No ingestion or optional model import."""

import asyncio

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
        return "generative" if self._synthesizer is not None else "extractive"

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
            return await asyncio.wait_for(
                asyncio.to_thread(use_case.answer, query), timeout=config.timeout_ms / 1000
            )
        except (KnowledgeError, TimeoutError):
            return PolicyAnswer(NO_EVIDENCE)
