"""Contract integration tests for Ollama NLU backend in FastAPI service."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.ollama_nlu import OllamaNLU
from smartevent_ai.infrastructure.settings import Settings


def make_mock_ollama_client(content: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"message": {"role": "assistant", "content": content}}
        return httpx.Response(200, json=body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_chat_integration_success() -> None:
    model_json = json.dumps(
        {
            "primary_intent": "SEARCH_EVENT",
            "proposed_action": "SEARCH_EVENTS",
            "entities": {"city": "Hà Nội", "category": "Acoustic"},
            "state_delta": [{"slot": "city", "value": "Hà Nội"}],
        }
    )
    mock_client = make_mock_ollama_client(model_json)
    app = create_app(Settings(nlu_backend="ollama", _env_file=None))
    app.state.chat._nlu = OllamaNLU(client=mock_client)

    with TestClient(app) as client:
        ready = client.get("/health/ready").json()
        assert ready["model_backend"] == "ollama"

        response = client.post("/api/v1/chat", json={"message": "Tìm concert acoustic tại Hà Nội"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "SEARCH_EVENT"
        assert data["state"]["city"] == "Hà Nội"


def test_ollama_chat_integration_fallback_on_network_failure() -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama daemon down")

    failing_client = httpx.Client(transport=httpx.MockTransport(failing_handler))
    app = create_app(Settings(nlu_backend="ollama", _env_file=None))
    app.state.chat._nlu = OllamaNLU(client=failing_client)

    with TestClient(app) as client:
        # Should gracefully fall back to RuleBasedNLU without 500
        response = client.post("/api/v1/chat", json={"message": "Tìm show ở Đà Nẵng"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "SEARCH_EVENT"
        assert data["state"]["city"] == "Đà Nẵng"
