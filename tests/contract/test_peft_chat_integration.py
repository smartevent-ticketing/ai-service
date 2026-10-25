"""End-to-end HTTP integration tests for PeftTransformerNLU in FastAPI service."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.infrastructure.settings import Settings


def test_chat_endpoint_with_peft_nlu_backend(monkeypatch) -> None:
    fake_model_json = json.dumps(
        {
            "primary_intent": "SEARCH_EVENT",
            "proposed_action": "SEARCH_EVENTS",
            "entities": {"city": "Hà Nội", "category": "Concert"},
            "state_delta": [{"slot": "city", "value": "Hà Nội"}],
        }
    )

    # Inject mock generator so test runs instantly without heavy GPU load
    def mock_generator(prompt: str) -> str:
        return fake_model_json

    app = create_app(Settings(_env_file=None))
    # Replace NLU in use case with mock-backed PeftTransformerNLU
    app.state.chat._nlu = PeftTransformerNLU(generator=mock_generator)

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "Tìm concert tại Hà Nội"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "SEARCH_EVENT"
        assert data["state"]["city"] == "Hà Nội"
        assert "Chưa thể xác minh" in data["answer"]


def test_chat_endpoint_peft_fallback_on_corrupted_model_output(monkeypatch) -> None:
    def corrupt_generator(prompt: str) -> str:
        return "I am an AI and this is not valid JSON {{}}"

    app = create_app(Settings(_env_file=None))
    app.state.chat._nlu = PeftTransformerNLU(generator=corrupt_generator)

    with TestClient(app) as client:
        # RuleBased fallback parses 'ở Đà Nẵng' cleanly
        response = client.post("/api/v1/chat", json={"message": "Tìm sự kiện ở Đà Nẵng"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "SEARCH_EVENT"
        assert data["state"]["city"] == "Đà Nẵng"


def test_chat_endpoint_peft_preserves_read_only_boundary() -> None:
    fake_gate_json = json.dumps(
        {
            "primary_intent": "BOOKING_GUIDANCE",
            "proposed_action": "EXPLAIN_WRITE_LIMITATION",
            "entities": {"quantity": 2},
        }
    )

    app = create_app(Settings(_env_file=None))
    app.state.chat._nlu = PeftTransformerNLU(generator=lambda p: fake_gate_json)

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "Giữ 2 vé VIP cho tôi"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "BOOKING_GUIDANCE"
        assert data["state"]["quantity"] == 2
        assert "không giữ" in data["answer"]
