"""Contract integration test for generative RAG in FastAPI service."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from knowledge_helpers import configure, make_bundle

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import (
    OllamaPolicySynthesizer,
)
from smartevent_ai.infrastructure.settings import Settings


def make_mock_ollama_synthesizer_client(answer_text: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"message": {"role": "assistant", "content": answer_text}}
        return httpx.Response(200, json=body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generative_rag_rejects_unsupported_claims_with_extractive_fallback(tmp_path: Path) -> None:
    catalog, output, manifest, _ = make_bundle(tmp_path)
    config = configure(tmp_path, catalog, output, manifest)

    generated_reply = (
        "Theo chính sách đã phê duyệt của SmartEvent, khi sự kiện bị hủy bỏ hoàn toàn "
        "bởi Ban tổ chức, khách hàng sẽ được hoàn 100% giá trị vé trong 7-14 ngày làm việc."
    )
    mock_client = make_mock_ollama_synthesizer_client(generated_reply)

    settings = Settings(
        config_dir=config,
        app_env="test",
        rag_backend="ollama",
        _env_file=None,
    )
    app = create_app(settings)
    # Inject mock client into the policy reader's synthesizer
    app.state.chat._policies._synthesizer = OllamaPolicySynthesizer(client=mock_client)

    with TestClient(app) as client:
        ready = client.get("/health/ready").json()
        assert ready["policy_retrieval"]["status"] == "ready"
        assert ready["policy_retrieval"]["answer_mode"] == "verified_extractive"

        response = client.post("/api/v1/chat", json={"message": "Chính sách hoàn tiền"})
        assert response.status_code == 200
        data = response.json()

        assert data["grounding"] == "APPROVED_CORPUS"
        assert data["answer"] != generated_reply
        assert "Ngoại lệ" in data["answer"]
        assert data["mode"] == "extractive_fallback"
        assert len(data["citations"]) > 0
        assert data["citations"][0]["source_id"] == "TEST-REFUND"


def test_generative_rag_chat_fallback_to_extractive_on_ollama_failure(tmp_path: Path) -> None:
    catalog, output, manifest, _ = make_bundle(tmp_path)
    config = configure(tmp_path, catalog, output, manifest)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama daemon down")

    failing_client = httpx.Client(transport=httpx.MockTransport(failing_handler))

    settings = Settings(
        config_dir=config,
        app_env="test",
        rag_backend="ollama",
        _env_file=None,
    )
    app = create_app(settings)
    app.state.chat._policies._synthesizer = OllamaPolicySynthesizer(client=failing_client)

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "Chính sách hoàn tiền"})
        assert response.status_code == 200
        data = response.json()

        assert data["grounding"] == "APPROVED_CORPUS"
        # Falls back to extractive passage
        assert "Trích đoạn từ chính sách" in data["answer"]
        assert "Ngoại lệ" in data["answer"]
        assert len(data["citations"]) > 0
