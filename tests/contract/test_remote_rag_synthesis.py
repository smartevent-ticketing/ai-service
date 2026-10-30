"""Remote RAG generation cannot bypass approved evidence or source revalidation."""

from types import SimpleNamespace

import pytest

from smartevent_ai.domain.evidence import EvidenceVerdict, classify
from smartevent_ai.domain.knowledge import Citation, PolicyAnswer
from smartevent_ai.infrastructure.knowledge_runtime import VerifiedSynthesizingPolicyReader


@pytest.mark.parametrize(
    "query",
    ["Làm thế nào để thanh toán", "Tôi muốn biết cách thanh toán", "Thanh toán như thế nào vậy"],
)
def test_vietnamese_question_fillers_do_not_drop_relevant_evidence(query):
    chunk = SimpleNamespace(text="Thanh toán qua VNPay.", context="Phương thức thanh toán")
    assert classify(query, chunk) is EvidenceVerdict.KEPT
    assert classify("thuế blockchain lượng tử", chunk) is EvidenceVerdict.DROPPED


@pytest.mark.parametrize(
    "candidate,expected_mode",
    [
        ("Nguồn TEST_ONLY: VNPay.", "verified_extractive"),
        ("Chắc chắn hoàn tiền 100%.", "extractive_fallback"),
        (None, "extractive_fallback"),
    ],
)
@pytest.mark.asyncio
async def test_remote_generation_uses_fresh_evidence_and_rejects_new_claims(
    candidate, expected_mode
):
    citation = Citation(
        "TEST-HELP", "1", "TEST_ONLY", "approved://test/help", "test-chunk", (), 0, 10
    )
    evidence = PolicyAnswer("Nguồn TEST_ONLY: VNPay.", (citation,))

    class Reader:
        calls = 0

        def status(self):
            return "ready"

        async def answer(self, query):
            self.calls += 1
            return evidence

    class Synthesizer:
        def synthesize(self, query, context):
            if candidate is None:
                raise RuntimeError("TEST_ONLY model failure")
            return candidate

    reader = Reader()
    answer = await VerifiedSynthesizingPolicyReader(reader, Synthesizer()).answer("Thanh toán?")
    assert reader.calls == 2
    assert answer.answer == evidence.answer and answer.citations == evidence.citations
    assert answer.mode == expected_mode


@pytest.mark.asyncio
async def test_revocation_during_remote_generation_prevents_returning_old_evidence():
    citation = Citation(
        "TEST-HELP", "1", "TEST_ONLY", "approved://test/help", "test-chunk", (), 0, 10
    )

    class Reader:
        calls = 0

        def status(self):
            return "ready"

        async def answer(self, query):
            self.calls += 1
            return (
                PolicyAnswer("Old evidence", (citation,))
                if self.calls == 1
                else PolicyAnswer("No evidence")
            )

    class Synthesizer:
        def synthesize(self, query, context):
            return context

    answer = await VerifiedSynthesizingPolicyReader(Reader(), Synthesizer()).answer("test")
    assert answer.answer == "No evidence" and not answer.citations
