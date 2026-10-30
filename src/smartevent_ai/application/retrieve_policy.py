"""Read-only evidence selection with eligibility checks before ranking and answer."""

from smartevent_ai.application.knowledge_ports import (
    Clock,
    EvidenceJudge,
    EvidenceRetriever,
    KnowledgeStore,
    PolicySynthesizer,
)
from smartevent_ai.domain.evidence import EvidenceVerdict, classify
from smartevent_ai.domain.knowledge import (
    Citation,
    KnowledgeChunk,
    KnowledgeError,
    PolicyAnswer,
    eligible_chunks,
)

NO_EVIDENCE = (
    "Chưa có đủ nguồn chính sách còn hiệu lực để trả lời. Vui lòng xem kênh hỗ trợ chính thức."
)


class DomainEvidenceJudge:
    """Offline-only judge adapter: pure domain classify, never raises."""

    def judge(
        self, query: str, chunks: tuple[KnowledgeChunk, ...]
    ) -> tuple[tuple[KnowledgeChunk, EvidenceVerdict], ...]:
        return tuple((chunk, classify(query, chunk)) for chunk in chunks)


class RetrievePolicy:
    def __init__(
        self,
        store: KnowledgeStore,
        retriever: EvidenceRetriever,
        clock: Clock,
        limit: int = 3,
        max_answer_chars: int = 6000,
        judge: EvidenceJudge | None = None,
        synthesizer: PolicySynthesizer | None = None,
    ) -> None:
        if not 1 <= limit <= 5 or not 256 <= max_answer_chars <= 16000:
            raise KnowledgeError("Invalid retrieval limits")
        self._store, self._retriever, self._clock = store, retriever, clock
        self._limit, self._max_answer_chars = limit, max_answer_chars
        self._judge = judge or DomainEvidenceJudge()
        self._synthesizer = synthesizer

    def answer(self, query: str) -> PolicyAnswer:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
            raise KnowledgeError("Invalid policy query")
        snapshot = self._store.snapshot(self._clock.now())
        allowed = eligible_chunks(snapshot, self._clock.now())
        ranked = self._retriever.rank(query, allowed, self._limit)
        if not ranked:
            return PolicyAnswer(NO_EVIDENCE)
        allowed_ids = {c.chunk_id for c in allowed}
        if len(ranked) > self._limit or any(c.chunk_id not in allowed_ids for c in ranked):
            raise KnowledgeError("Retriever returned unauthorized evidence")
        try:
            verdicts = dict((c.chunk_id, v) for c, v in self._judge.judge(query, ranked))
        except Exception:
            verdicts = {}
        # Missing verdicts never turn unchecked evidence into approved claims.
        kept = [
            c
            for c in ranked
            if verdicts.get(c.chunk_id, EvidenceVerdict.DROPPED)
            in (EvidenceVerdict.KEPT, EvidenceVerdict.CONFLICTS)
        ]
        if not kept:
            return PolicyAnswer(NO_EVIDENCE)
        undercutting = {
            c.chunk_id for c in kept if verdicts.get(c.chunk_id) is EvidenceVerdict.CONFLICTS
        }
        current = self._store.snapshot(self._clock.now())
        if (
            current.release_id != snapshot.release_id
            or current.catalog_sha256 != snapshot.catalog_sha256
        ):
            raise KnowledgeError("Knowledge authority changed during retrieval")
        fresh = {c.chunk_id for c in eligible_chunks(current, self._clock.now())}
        sources = {(s.source_id, s.version, s.content_sha256): s for s in current.sources}
        documents = {
            (d.source.source_id, d.source.version, d.source.content_sha256): d
            for d in current.documents
        }
        citations: list[Citation] = []
        passages: list[str] = []
        length = len("Trích đoạn từ chính sách đã được phê duyệt:\n\n")
        parents: set[tuple[str, str, int, int]] = set()
        for chunk in kept:
            if chunk.chunk_id not in fresh:
                raise KnowledgeError("Evidence expired or revoked during retrieval")
            source = sources[chunk.source_id, chunk.source_version, chunk.source_sha256]
            parent = chunk.source_id, chunk.source_version, chunk.parent_start, chunk.parent_end
            if parent in parents:
                continue
            document = documents[chunk.source_id, chunk.source_version, chunk.source_sha256]
            excerpt = document.text[chunk.parent_start : chunk.parent_end].strip()
            marker = (
                "[BẰNG CHỨNG PHẢN BIỆN — cần đối chiếu] " if chunk.chunk_id in undercutting else ""
            )
            passage = f"[{len(citations) + 1}] {marker}{' > '.join(chunk.heading_path)}\n{excerpt}"
            if length + len(passage) + 2 > self._max_answer_chars:
                if not citations:
                    return PolicyAnswer(NO_EVIDENCE)
                continue  # Never truncate an individual clause/exception.
            length += len(passage) + 2
            parents.add(parent)
            passages.append(passage)
            citations.append(
                Citation(
                    source.source_id,
                    source.version,
                    source.title,
                    source.canonical_uri,
                    chunk.chunk_id,
                    chunk.heading_path,
                    chunk.parent_start,
                    chunk.parent_end,
                )
            )
        if not citations:
            return PolicyAnswer(NO_EVIDENCE)
        raw_passages = "Trích đoạn từ chính sách đã được phê duyệt:\n\n" + "\n\n".join(passages)
        if self._synthesizer is not None:
            try:
                synthesized = self._synthesizer.synthesize(query, raw_passages)
                # Conservative verifier: until an independently evaluated entailment
                # checker is approved, accept only the complete extractive evidence.
                # Substrings may omit an exception or invert a source's meaning.
                if isinstance(synthesized, str) and " ".join(synthesized.split()) == " ".join(
                    raw_passages.split()
                ):
                    fresh_snapshot = self._store.snapshot(self._clock.now())
                    if (
                        fresh_snapshot.catalog_sha256 != current.catalog_sha256
                        or fresh_snapshot.release_id != current.release_id
                    ):
                        raise KnowledgeError("Evidence authority changed during generation")
                    if any(
                        c.chunk_id
                        not in {
                            x.chunk_id for x in eligible_chunks(fresh_snapshot, self._clock.now())
                        }
                        for c in citations
                    ):
                        raise KnowledgeError("Evidence expired during generation")
                    return PolicyAnswer(
                        synthesized.strip(), tuple(citations), "verified_extractive"
                    )
            except KnowledgeError:
                return PolicyAnswer(NO_EVIDENCE)
            except Exception:
                synthesized = None  # Explicitly discard failed generation before fallback.
        final = self._store.snapshot(self._clock.now())
        valid = {c.chunk_id for c in eligible_chunks(final, self._clock.now())}
        if (
            final.release_id != current.release_id
            or final.catalog_sha256 != current.catalog_sha256
            or any(c.chunk_id not in valid for c in citations)
        ):
            return PolicyAnswer(NO_EVIDENCE)
        return PolicyAnswer(
            raw_passages,
            tuple(citations),
            "extractive_fallback" if self._synthesizer else "extractive",
        )
