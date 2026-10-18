"""Small-corpus BM25 baseline. Only eligible chunks are passed to this adapter."""

import math
import re
import unicodedata
from collections import Counter

from smartevent_ai.domain.knowledge import KnowledgeChunk

_STOP = frozenset(
    "toi muon hoi cho biet ve cac cua la va co duoc nhu nao the nao mot nay xin".split()
)


def terms(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [word for word in re.findall(r"\w+", text) if word not in _STOP]


class BM25Retriever:
    def rank(
        self, query: str, chunks: tuple[KnowledgeChunk, ...], limit: int
    ) -> tuple[KnowledgeChunk, ...]:
        query_terms = set(terms(query))
        if not chunks or not query_terms:
            return ()
        counts = [Counter(terms(c.context + "\n" + c.text)) for c in chunks]
        lengths = [sum(c.values()) for c in counts]
        average = sum(lengths) / len(counts) or 1
        frequencies = {word: sum(word in c for c in counts) for word in query_terms}
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk, count, length in zip(chunks, counts, lengths, strict=True):
            if not query_terms.intersection(terms(chunk.text)):
                continue  # A matching document title alone is not answer evidence.
            matched = query_terms.intersection(count)
            if len(matched) / len(query_terms) < 0.5:
                continue
            score = 0.0
            for word in matched:
                freq = count[word]
                idf = math.log(
                    1 + (len(chunks) - frequencies[word] + 0.5) / (frequencies[word] + 0.5)
                )
                score += idf * (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * length / average))
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda row: (-row[0], row[1].chunk_id))
        return tuple(c for _, c in scored[:limit])
