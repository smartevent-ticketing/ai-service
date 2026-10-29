"""Small-corpus BM25 baseline. Only eligible chunks are passed to this adapter."""

import math
import re
import unicodedata
from collections import Counter

from smartevent_ai.domain.knowledge import KnowledgeChunk

_STOP = frozenset(
    "toi muon hoi cho biet ve cac cua la va co duoc nhu nao the nao mot nay xin "
    "nhung cach gi bang o dau vi tai sao bao nhieu lam de minh ban em chi con thi nua nhe a vay".split()
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
        known_frequencies = [frequency for frequency in frequencies.values() if frequency]
        if not known_frequencies:
            return ()
        # Specific query evidence (e.g. a named payment method) must not be replaced
        # by generic words such as "hỗ trợ" present in unrelated help sections.
        rarest = {
            word for word, frequency in frequencies.items() if frequency == min(known_frequencies)
        }
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk, count, length in zip(chunks, counts, lengths, strict=True):
            if not rarest.issubset(count):
                continue
            if not query_terms.intersection(terms(chunk.text)):
                continue  # A matching document title alone is not answer evidence.
            matched = query_terms.intersection(count)
            if len(matched) < min(2, len(query_terms)):
                continue
            if len(matched) / len(query_terms) < 0.5:
                continue
            score = 0.0
            for word in matched:
                freq = count[word]
                idf = math.log(
                    1 + (len(chunks) - frequencies[word] + 0.5) / (frequencies[word] + 0.5)
                )
                score += idf * (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * length / average))
            # A section's actual question is more specific than a repeated document title.
            heading = set(terms(chunk.heading_path[-1])) if chunk.heading_path else set()
            for word in query_terms.intersection(heading):
                score += 2 * math.log(
                    1 + (len(chunks) - frequencies[word] + 0.5) / (frequencies[word] + 0.5)
                )
            body_coverage = len(query_terms.intersection(terms(chunk.text))) / len(query_terms)
            heading_coverage = len(query_terms.intersection(heading)) / len(query_terms)
            coverage = max(body_coverage, heading_coverage)
            score *= coverage * coverage
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda row: (-row[0], row[1].chunk_id))
        return tuple(c for _, c in scored[:limit])
