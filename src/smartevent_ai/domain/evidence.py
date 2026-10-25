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

_STOP = frozenset(
    "toi muon hoi la gi cai nay kia va hoac cua trong voi cho co khong nao a nhe "
    "xin biet ve duoc".split()
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return " ".join("".join(c for c in normalized if not unicodedata.combining(c)).split())


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", _normalize(text)) if w not in _STOP}


def _has_injection(text: str) -> bool:
    return _INJECTION.search(text) is not None


def _contradicts_premise(query: str, text: str) -> bool:
    # Conservative refund-only baseline: compare exact universal assertions.
    # Open questions, conditional clauses and ordinary exceptions are not
    # premise contradictions. Broader entailment requires a separate evaluator.
    premise, evidence = _refund_claim(query), _refund_claim(text)
    return premise != 0 and evidence == -premise


def _refund_claim(text: str) -> int:
    norm = _normalize(text)
    if re.fullmatch(r"(?:moi|tat ca|bat ky) ve (?:deu )?duoc hoan tien[.!?]*", norm):
        return 1
    if re.fullmatch(r"khong bao gio hoan tien(?: trong moi truong hop)?[.!?]*", norm):
        return -1
    return 0


def _relevance_ratio(query: str, text: str, context: str) -> float:
    query_terms = _terms(query)
    if not query_terms or not query_terms.intersection(_terms(text)):
        return 0.0  # A matching title alone cannot make unrelated text evidence.
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
