"""Unit tests for PolicySynthesizer adapter and RetrievePolicy generative integration."""

from __future__ import annotations


import httpx
import pytest

from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import (
    OllamaPolicySynthesizer,
)
from smartevent_ai.application.retrieve_policy import RetrievePolicy


def make_mock_client(response_content: str, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"message": {"role": "assistant", "content": response_content}}
        return httpx.Response(status_code=status_code, json=body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_synthesizer_generates_natural_answer() -> None:
    expected_answer = (
        "Khi sự kiện bị hủy bỏ hoàn toàn bởi Ban tổ chức, SmartEvent sẽ hoàn tiền 100% "
        "vào tài khoản của bạn trong 7-14 ngày làm việc."
    )
    client = make_mock_client(expected_answer)
    synthesizer = OllamaPolicySynthesizer(client=client)

    result = synthesizer.synthesize(
        query="Sự kiện bị hủy tôi có được hoàn tiền không?",
        context="[1] Điều khoản: Hủy sự kiện hoàn 100% trong 7-14 ngày.",
    )

    assert result == expected_answer


def test_ollama_synthesizer_falls_back_to_raw_context_on_network_error() -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama daemon unreachable")

    client = httpx.Client(transport=httpx.MockTransport(failing_handler))
    synthesizer = OllamaPolicySynthesizer(client=client)

    raw_context = "[1] Điều khoản: Hủy sự kiện hoàn 100% trong 7-14 ngày."
    result = synthesizer.synthesize(
        query="Sự kiện bị hủy tôi có được hoàn tiền không?",
        context=raw_context,
    )

    # Safe fallback to raw context without raising exception
    assert result == raw_context


def test_ollama_synthesizer_falls_back_on_timeout() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Ollama generation timed out")

    client = httpx.Client(transport=httpx.MockTransport(timeout_handler))
    synthesizer = OllamaPolicySynthesizer(client=client)

    raw_context = "[1] Điều khoản trích dẫn"
    result = synthesizer.synthesize(query="Hoàn tiền", context=raw_context)

    assert result == raw_context


def test_retrieve_policy_delegates_to_synthesizer_when_provided(tmp_path) -> None:
    from knowledge_helpers import NOW, make_bundle  # type: ignore[import-not-found]
    from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
    from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
    from smartevent_ai.tooling.offline_jobs.evaluate import FrozenClock

    class MemoryStore:
        def __init__(self, snapshot):
            self.value = snapshot

        def snapshot(self, now):
            return self.value

    class EchoSynthesizer:
        def synthesize(self, query: str, context: str) -> str:
            return f"NATURAL ANSWER FOR: {query}"

    _, _, _, artifacts = make_bundle(tmp_path)
    snapshot = ArtifactKnowledgeStore(artifacts, True).snapshot(NOW)

    # 1. Extractive mode (no synthesizer)
    reader_extractive = RetrievePolicy(
        MemoryStore(snapshot), BM25Retriever(), FrozenClock(NOW), synthesizer=None
    )
    answer_ext = reader_extractive.answer("chính sách hoàn tiền")
    assert "Trích đoạn từ chính sách" in answer_ext.answer
    assert answer_ext.citations

    # 2. Generative mode (with synthesizer)
    reader_generative = RetrievePolicy(
        MemoryStore(snapshot),
        BM25Retriever(),
        FrozenClock(NOW),
        synthesizer=EchoSynthesizer(),
    )
    answer_gen = reader_generative.answer("chính sách hoàn tiền")
    assert answer_gen.answer == "NATURAL ANSWER FOR: chính sách hoàn tiền"
    # Citations must be preserved!
    assert answer_gen.citations == answer_ext.citations


def test_ollama_synthesizer_empty_response_returns_context() -> None:
    client = make_mock_client("")
    synthesizer = OllamaPolicySynthesizer(client=client)
    res = synthesizer.synthesize("test", "[1] Context passage")
    assert res == "[1] Context passage"


def test_peft_synthesizer_with_generator_success_and_fallback(tmp_path) -> None:
    from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import (
        PeftPolicySynthesizer,
    )

    # Success case with generator
    synth = PeftPolicySynthesizer(generator=lambda p: "GENERATED ANSWER")
    res = synth.synthesize("query", "context")
    assert res == "GENERATED ANSWER"

    # Generator error falls back to context
    def err_gen(p: str) -> str:
        raise RuntimeError("GPU fail")

    synth_err = PeftPolicySynthesizer(generator=err_gen)
    assert synth_err.synthesize("query", "context") == "context"

    # Missing adapter path raises on ensure_loaded
    missing_synth = PeftPolicySynthesizer(adapter_path=tmp_path / "nonexistent")
    with pytest.raises(FileNotFoundError):
        missing_synth._ensure_loaded()


def test_ollama_policy_synthesizer_close() -> None:
    client = make_mock_client("ok")
    synth = OllamaPolicySynthesizer(client=client)
    assert not client.is_closed
    synth.close()
    assert client.is_closed


def test_peft_policy_synthesizer_threading_lock() -> None:
    import threading
    from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import (
        PeftPolicySynthesizer,
    )

    synth = PeftPolicySynthesizer()
    assert isinstance(synth._lock, type(threading.Lock()))
