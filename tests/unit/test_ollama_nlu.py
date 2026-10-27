"""Unit tests for OllamaNLU outbound adapter following TDD."""

from __future__ import annotations

import json

import httpx

from smartevent_ai.adapters.outbound.ollama_nlu import OllamaNLU
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Intent,
    Scope,
)


def make_mock_client(response_data: dict | str, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            json.dumps(response_data).encode("utf-8")
            if isinstance(response_data, dict)
            else response_data.encode("utf-8")
        )
        return httpx.Response(status_code=status_code, content=content, request=request)

    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_parses_ollama_json_chat_response() -> None:
    ollama_payload = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "primary_intent": "SEARCH_EVENT",
                    "proposed_action": "SEARCH_EVENTS",
                    "entities": {"city": "Hà Nội", "category": "Concert"},
                    "state_delta": [{"slot": "city", "value": "Hà Nội"}],
                }
            ),
        }
    }
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Tìm concert ở Hà Nội", DialogueState())

    assert result.intent == Intent.SEARCH_EVENT
    assert result.patch.city == "Hà Nội"
    assert result.needs_clarification is False


def test_parses_markdown_wrapped_json_from_ollama() -> None:
    raw_markdown = """```json
{
    "primary_intent": "TICKET_RECOMMEND",
    "proposed_action": "RUN_TICKET_OPTIMIZER",
    "entities": {"quantity": 2, "city": "TP Hồ Chí Minh"},
    "state_delta": [{"slot": "quantity", "value": 2}]
}
```"""
    ollama_payload = {"message": {"role": "assistant", "content": raw_markdown}}
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Tôi muốn mua 2 vé ở Sài Gòn", DialogueState())

    assert result.intent == Intent.TICKET_RECOMMEND
    assert result.patch.quantity == 2
    assert result.patch.city in ("Hồ Chí Minh", "TP Hồ Chí Minh")


def test_out_of_range_quantity_triggers_clarification() -> None:
    ollama_payload = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "primary_intent": "TICKET_RECOMMEND",
                    "entities": {"quantity": 30},
                }
            ),
        }
    }
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Mua 30 vé", DialogueState())

    assert result.needs_clarification is True
    assert result.clarification_reason == ClarificationReason.QUANTITY_OUT_OF_RANGE
    assert result.patch.quantity is None


def test_malformed_json_from_ollama_falls_back_to_rule_nlu() -> None:
    ollama_payload = {"message": {"role": "assistant", "content": "Đây không phải là JSON"}}
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    # Should gracefully fall back to rule-based parse without exception
    result = nlu.parse("Tìm concert ở Đà Nẵng", DialogueState())

    assert result.intent == Intent.SEARCH_EVENT
    assert result.patch.city == "Đà Nẵng"


def test_network_or_connection_error_falls_back_to_rule_nlu() -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by Ollama daemon")

    client = httpx.Client(transport=httpx.MockTransport(failing_handler))
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Xin chào", DialogueState())

    assert result.intent == Intent.GREETING


def test_read_only_protection_maps_to_booking_guidance() -> None:
    ollama_payload = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "primary_intent": "BOOKING_GUIDANCE",
                    "proposed_action": "EXPLAIN_WRITE_LIMITATION",
                    "entities": {"quantity": 2},
                }
            ),
        }
    }
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Giữ vé giúp tôi ngay", DialogueState())

    assert result.intent == Intent.BOOKING_GUIDANCE
    assert result.patch.quantity == 2


def test_ollama_nlu_parses_budget_and_case_insensitive_intent() -> None:
    ollama_payload = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "primary_intent": "ticket_recommend",
                    "entities": {
                        "budget_amount": 500000,
                        "budget_scope": "TOTAL",
                        "city": "Hà Nội",
                    },
                }
            ),
        }
    }
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Tìm vé dưới 500k tổng", DialogueState())

    assert result.intent == Intent.TICKET_RECOMMEND
    assert result.patch.budget_amount == 500000
    assert result.patch.budget_scope == Scope.TOTAL
    assert result.patch.active_intent == Intent.TICKET_RECOMMEND

    nlu.close()


def test_ollama_nlu_budget_out_of_range_clarifies() -> None:
    ollama_payload = {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "primary_intent": "TICKET_RECOMMEND",
                    "entities": {
                        "budget_amount": 2_000_000_000,
                    },
                }
            ),
        }
    }
    client = make_mock_client(ollama_payload)
    nlu = OllamaNLU(client=client)

    result = nlu.parse("Vé dưới 2 tỷ", DialogueState())

    assert result.needs_clarification is True
    assert result.clarification_reason == ClarificationReason.BUDGET_OUT_OF_RANGE


def test_ollama_nlu_includes_previous_state_in_prompt_and_resolves_budget_scope() -> None:
    captured_payload = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        response_content = json.dumps(
            {
                "primary_intent": "TICKET_RECOMMEND",
                "entities": {
                    "budget_scope": "PER_TICKET",
                },
            }
        )
        return httpx.Response(
            status_code=200,
            content=json.dumps({"message": {"role": "assistant", "content": response_content}}).encode("utf-8"),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    nlu = OllamaNLU(client=client)

    prev_state = DialogueState(
        active_intent=Intent.TICKET_RECOMMEND,
        city="Hà Nội",
        quantity=2,
        budget_amount=500_000,
        search_query="Rock concert",
    )
    result = nlu.parse("mỗi vé", prev_state)

    assert captured_payload is not None
    user_msg = captured_payload["messages"][1]["content"]
    assert "Trạng thái trước:" in user_msg
    assert "active_intent: TICKET_RECOMMEND" in user_msg
    assert "city: Hà Nội" in user_msg
    assert "budget_amount: 500000" in user_msg
    assert result.patch.budget_scope == Scope.PER_TICKET

