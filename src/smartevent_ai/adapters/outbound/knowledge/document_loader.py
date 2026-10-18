"""Bounded local Markdown/TXT loading; no crawling or arbitrary remote URLs."""

import re
import unicodedata
from pathlib import Path, PurePosixPath

from smartevent_ai.adapters.outbound.knowledge.contracts import read_bytes
from smartevent_ai.domain.knowledge import KnowledgeError, LoadedDocument, SourceMetadata, digest

_INJECTION = re.compile(
    r"ignore\s+(all\s+)?previous\s+instructions|<\|im_start\|>|\[INST\]|"
    r"bỏ qua (mọi |các )?(hướng dẫn|chỉ dẫn) (trước|hệ thống)",
    re.I,
)


def validate_text(text: str) -> None:
    if not text.strip() or "\x00" in text or _INJECTION.search(text):
        raise KnowledgeError("Empty, binary or quarantined instruction content")
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise KnowledgeError("Unsupported control characters")


class LocalDocumentLoader:
    def __init__(self, root: Path, max_bytes: int = 1_000_000) -> None:
        self._root, self._max_bytes = root.resolve(strict=True), max_bytes

    def load(self, relative_path: str, source: SourceMetadata) -> LoadedDocument:
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in relative_path
            or ":" in relative_path
            or relative.suffix.lower() not in (".md", ".txt")
        ):
            raise KnowledgeError("Only relative Markdown/TXT corpus paths are accepted")
        target = self._root.joinpath(*relative.parts)
        try:
            if not target.resolve(strict=True).is_relative_to(self._root):
                raise KnowledgeError("Corpus path escapes root")
        except OSError as exc:
            raise KnowledgeError("Missing corpus source") from exc
        for ancestor in (target, *target.parents):
            if ancestor == self._root:
                break
            if ancestor.is_symlink():
                raise KnowledgeError("Symlink corpus sources are forbidden")
        raw = read_bytes(target, self._max_bytes)
        if digest(raw) != source.content_sha256:
            raise KnowledgeError("Source checksum differs from approved catalog")
        try:
            text = unicodedata.normalize(
                "NFC", raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            )
        except UnicodeError as exc:
            raise KnowledgeError("Source must be UTF-8") from exc
        validate_text(text)
        return LoadedDocument(source, text)
