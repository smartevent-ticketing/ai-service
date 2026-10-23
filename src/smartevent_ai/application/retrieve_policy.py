"""Read-only evidence selection with eligibility checks before ranking and answer."""

from smartevent_ai.application.knowledge_ports import (
    Clock,
    EvidenceJudge,
    EvidenceRetriever,
    KnowledgeStore,
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
    ) -> None:
        if not 1 <= limit <= 5 or not 256 <= max_answer_chars <= 16000:
            raise KnowledgeError("Invalid retrieval limits")
        self._store, self._retriever, self._clock = store, retriever, clock
        self._limit, self._max_answer_chars = limit, max_answer_chars
        self._judge = judge or DomainEvidenceJudge()

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
        # Judge unavailable (empty verdicts on non-empty ranked) falls back to
        # plain BM25 ranking: every chunk treated as KEPT, never fail-closed.
        kept = [
            c
            for c in ranked
            if verdicts.get(c.chunk_id, EvidenceVerdict.KEPT) is not EvidenceVerdict.DROPPED
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
        return PolicyAnswer(
            "Trích đoạn từ chính sách đã được phê duyệt:\n\n" + "\n\n".join(passages),
            tuple(citations),
        )
