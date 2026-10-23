"""Deterministic, read-source-only ingestion. Publication is an offline concern."""

from smartevent_ai.application.knowledge_ports import DocumentChunker, DocumentLoader
from smartevent_ai.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeError,
    LoadedDocument,
    SourceMetadata,
)


class IngestKnowledge:
    def __init__(
        self, loader: DocumentLoader, chunker: DocumentChunker, max_total_chunks: int = 10000
    ) -> None:
        self._loader, self._chunker = loader, chunker
        self._max_total_chunks = max_total_chunks

    def build_with_documents(
        self, sources: tuple[tuple[str, SourceMetadata], ...]
    ) -> tuple[tuple[KnowledgeChunk, ...], dict[tuple[str, str, str], LoadedDocument]]:
        seen: set[tuple[str, str]] = set()
        chunks: list[KnowledgeChunk] = []
        documents: dict[tuple[str, str, str], LoadedDocument] = {}
        for path, source in sorted(sources, key=lambda row: (row[1].source_id, row[1].version)):
            identity = source.source_id, source.version
            if identity in seen:
                raise KnowledgeError("Duplicate source/version")
            seen.add(identity)
            document = self._loader.load(path, source)
            documents[source.source_id, source.version, source.content_sha256] = document
            chunks.extend(self._chunker.split(document))
            if len(chunks) > self._max_total_chunks:
                raise KnowledgeError("Corpus exceeds chunk limit")
        if not chunks:
            raise KnowledgeError("Empty corpus")
        return tuple(chunks), documents

    def build(self, sources: tuple[tuple[str, SourceMetadata], ...]) -> tuple[KnowledgeChunk, ...]:
        chunks, _ = self.build_with_documents(sources)
        return chunks
