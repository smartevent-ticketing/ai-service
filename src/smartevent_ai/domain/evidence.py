"""Pure offline evidence verdicts. No files, frameworks or model libraries."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Any


class EvidenceVerdict(StrEnum):
    KEPT = "kept"
    CONFLICTS = "conflicts"
    DROPPED = "dropped"


_INJECTION = re.compile(
    r"ignore\s+(all\s+)?previous\s+instructions"
    r"|<\|im_start\|>"
    r"|\[INST\]"
    r"|bỏ qua (mọi |các )?(hướng dẫn|chỉ dẫn) (trước|hệ thống)",
    re.IGNORECASE,
)

_CONTRADICTION_MARKERS = (
    "không bao giờ",
    "không được",
    "không áp dụng",
    "ngoại trừ",
    "trừ khi",
    "never",
    "not applicable",
    "except",
)

_STOP = frozenset(
    "tôi muốn hỏi là gì cái này kia và hoặc của trong với cho có không gì nào à ạ nhé".split()
)


def _terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    stripped = "".join(c for c in normalized if not unicodedata.combining(c))
    return {w for w in re.findall(r"\w+", stripped) if w not in _STOP}


def _has_injection(text: str) -> bool:
    return _INJECTION.search(text) is not None


def _contradicts_premise(query: str, text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CONTRADICTION_MARKERS)


def _relevance_ratio(query: str, text: str, context: str) -> float:
    query_terms = _terms(query)
    if not query_terms:
        return 0.0
    haystack = _terms(context + "\n" + text)
    matched = query_terms.intersection(haystack)
    return len(matched) / len(query_terms)


def classify(query: Any, chunk: Any) -> EvidenceVerdict:
    try:
        text = chunk.text
        context = getattr(chunk, "context", "")
        if not isinstance(text, str) or not isinstance(context, str):
            return EvidenceVerdict.DROPPED
        if _has_injection(text):
            return EvidenceVerdict.DROPPED
        if not isinstance(query, str) or not query.strip():
            return EvidenceVerdict.DROPPED
        if _contradicts_premise(query, text):
            return EvidenceVerdict.CONFLICTS
        if _relevance_ratio(query, text, context) < 0.5:
            return EvidenceVerdict.DROPPED
        if not text.strip():
            return EvidenceVerdict.DROPPED
        return EvidenceVerdict.KEPT
    except Exception:
        return EvidenceVerdict.DROPPED
