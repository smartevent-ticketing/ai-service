"""Structure-aware chunking with exact tokenizer budgets and source offsets."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Iterator

from smartevent_ai.application.knowledge_ports import TokenCounter
from smartevent_ai.domain.knowledge import (
    ChunkingPolicy,
    KnowledgeChunk,
    KnowledgeError,
    LoadedDocument,
    digest,
    fingerprint,
)


def _sections(text: str) -> Iterator[tuple[int, int, tuple[str, ...]]]:
    headings: list[tuple[int, str]] = []
    offset = start = 0
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s*(```+|~~~+)", line)
        if marker:
            value = marker[1][0]
            fence = None if fence == value else value
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line) if not fence else None
        if heading:
            if text[start:offset].strip():
                yield start, offset, tuple(h for _, h in headings)
            level = len(heading[1])
            headings = [(n, h) for n, h in headings if n < level]
            headings.append((level, heading[2]))
            start = offset + len(line)
        offset += len(line)
    if text[start:offset].strip():
        yield start, offset, tuple(h for _, h in headings)


def _parts(text: str, start: int, end: int) -> Iterator[tuple[int, int, str, bool]]:
    """Split tables from prose; repeat table headers in each chunk's context."""
    lines = text[start:end].splitlines(keepends=True)
    positions = [start]
    for line in lines:
        positions.append(positions[-1] + len(line))
    cursor = i = 0
    while i + 1 < len(lines):
        if lines[i].lstrip().startswith("|") and re.fullmatch(
            r"\s*\|?[\s:|\-]+\|\s*", lines[i + 1]
        ):
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            if positions[cursor] < positions[i] and text[positions[cursor] : positions[i]].strip():
                yield positions[cursor], positions[i], "", False
            if j == i + 2:
                raise KnowledgeError("Table has no data rows")
            yield positions[i + 2], positions[j], lines[i] + lines[i + 1], True
            cursor = i = j
        else:
            i += 1
    if cursor < len(lines) and text[positions[cursor] : end].strip():
        yield positions[cursor], end, "", False


class StructureChunker:
    def __init__(self, tokenizer: TokenCounter, policy: ChunkingPolicy = ChunkingPolicy()) -> None:
        if policy.max_tokens > int(tokenizer.profile["context_window"]):
            raise KnowledgeError("Chunk budget exceeds embedding tokenizer context")
        self._tokenizer, self._policy = tokenizer, policy

    @property
    def profile(self) -> dict[str, object]:
        return {
            **asdict(self._policy),
            "normalization": "NFC_LF_v1",
            "tokenizer": self._tokenizer.profile,
        }

    def split(self, document: LoadedDocument) -> tuple[KnowledgeChunk, ...]:
        text = document.text
        normalized_hash, profile_hash = digest(text.encode()), fingerprint(self.profile)
        result: list[KnowledgeChunk] = []
        for parent_start, parent_end, headings in _sections(text):
            for start, end, table_header, is_table in _parts(text, parent_start, parent_end):
                context = document.source.title + "\n" + " > ".join(headings) + "\n" + table_header
                if self._tokenizer.count(context) >= self._policy.max_tokens - 2:
                    raise KnowledgeError("Headings/table header consume token budget")
                position = start
                while position < end:
                    if not text[position:end].strip():
                        break
                    stop = self._fit(text, context, position, end)
                    if stop < end:
                        boundaries = [
                            m.end() + position
                            for m in re.finditer(r"\n\s*\n|\n|[.!?;]\s+|\s+", text[position:stop])
                        ]
                        if is_table:
                            boundaries = [
                                m.end() + position for m in re.finditer(r"\n", text[position:stop])
                            ]
                            if not boundaries:
                                raise KnowledgeError("Table row exceeds token budget")
                        usable = [b for b in boundaries if b > position + (stop - position) // 2]
                        if usable:
                            stop = usable[-1]
                        elif is_table:
                            stop = boundaries[-1]
                    body = text[position:stop]
                    count = self._tokenizer.count(context + body)
                    if not body.strip() or stop <= position or count > self._policy.max_tokens:
                        raise KnowledgeError("Chunker could not make bounded progress")
                    result.append(
                        KnowledgeChunk(
                            document.source.source_id,
                            document.source.version,
                            document.source.content_sha256,
                            normalized_hash,
                            body,
                            context,
                            headings,
                            position,
                            stop,
                            count,
                            profile_hash,
                            parent_start,
                            parent_end,
                        )
                    )
                    if len(result) > self._policy.max_chunks:
                        raise KnowledgeError("Document exceeds chunk count limit")
                    if stop == end:
                        break
                    next_position = stop
                    if not is_table and self._policy.overlap_tokens:
                        candidates = [
                            m.end() + position for m in re.finditer(r"\s+", text[position:stop])
                        ]
                        for candidate in candidates:
                            if (
                                candidate > position
                                and candidate < stop
                                and self._tokenizer.count(text[candidate:stop])
                                <= self._policy.overlap_tokens
                            ):
                                next_position = candidate
                                break
                    position = next_position
        if not result:
            raise KnowledgeError("Document has no extractable policy content")
        return tuple(result)

    def _fit(self, text: str, context: str, start: int, end: int) -> int:
        low, high = start, min(end, start + 100_000)
        # Token counts need not be strictly monotonic under BPE. Recheck the
        # selected prefix and conservatively shrink; exceeding budgets is forbidden.
        while low < high:
            middle = (low + high + 1) // 2
            if self._tokenizer.count(context + text[start:middle]) <= self._policy.max_tokens:
                low = middle
            else:
                high = middle - 1
        while (
            low > start
            and self._tokenizer.count(context + text[start:low]) > self._policy.max_tokens
        ):
            low -= 1
        return low
