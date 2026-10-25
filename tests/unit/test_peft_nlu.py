"""Unit tests for PeftTransformerNLU adapter following TDD."""

from __future__ import annotations

import json


from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Intent,
)


class FakeGenerator:
    """Mock generator returning predetermined text for fast unit testing."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_prompt = None

    def __call__(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response_text


def test_parses_clean_json_into_understanding() -> None:
    fake_json = json.dumps(
        {
            "primary_intent": "SEARCH_EVENT",
            "proposed_action": "SEARCH_EVENTS",
            "entities": {"city": "Hà Nội", "category": "Acoustic"},
            "state_delta": [{"slot": "city", "value": "Hà Nội"}],
        }
    )
    nlu = PeftTransformerNLU(generator=FakeGenerator(fake_json))
    result = nlu.parse("Tìm sự kiện acoustic tại Hà Nội", DialogueState())

    assert result.intent == Intent.SEARCH_EVENT
    assert result.patch.city == "Hà Nội"
    assert result.needs_clarification is False


def test_parses_markdown_wrapped_json() -> None:
    raw_markdown = """```json
{
    "primary_intent": "TICKET_RECOMMEND",
    "proposed_action": "RUN_TICKET_OPTIMIZER",
    "entities": {"quantity": 2, "city": "TP Hồ Chí Minh"},
    "state_delta": [{"slot": "quantity", "value": 2}]
}
```"""
    nlu = PeftTransformerNLU(generator=FakeGenerator(raw_markdown))
    result = nlu.parse("Tôi muốn mua 2 vé ở Sài Gòn", DialogueState())

    assert result.intent == Intent.TICKET_RECOMMEND
    assert result.patch.quantity == 2
    assert result.patch.city == "Hồ Chí Minh" or result.patch.city == "TP Hồ Chí Minh"


def test_out_of_range_quantity_triggers_clarification() -> None:
    fake_json = json.dumps(
        {
            "primary_intent": "TICKET_RECOMMEND",
            "entities": {"quantity": 25},
        }
    )
    nlu = PeftTransformerNLU(generator=FakeGenerator(fake_json))
    result = nlu.parse("Mua 25 vé", DialogueState())

    assert result.needs_clarification is True
    assert result.clarification_reason == ClarificationReason.QUANTITY_OUT_OF_RANGE
    assert result.patch.quantity is None


def test_malformed_json_falls_back_to_rule_nlu_safely() -> None:
    bad_output = "Xin lỗi, tôi là AI và không hiểu câu này: error 404"
    nlu = PeftTransformerNLU(generator=FakeGenerator(bad_output))

    # Should not raise exception, should fall back to rule-based parsing
    result = nlu.parse("Tìm concert ở Hà Nội", DialogueState())

    assert result.intent == Intent.SEARCH_EVENT
    assert result.patch.city == "Hà Nội"


def test_generator_exception_falls_back_to_rule_nlu() -> None:
    def failing_generator(prompt: str) -> str:
        raise RuntimeError("CUDA out of memory")

    nlu = PeftTransformerNLU(generator=failing_generator)
    result = nlu.parse("Xin chào", DialogueState())

    assert result.intent == Intent.GREETING


def test_read_only_limitation_maps_to_guidance() -> None:
    fake_json = json.dumps(
        {
            "primary_intent": "BOOKING_GUIDANCE",
            "proposed_action": "EXPLAIN_WRITE_LIMITATION",
            "entities": {"quantity": 2},
        }
    )
    nlu = PeftTransformerNLU(generator=FakeGenerator(fake_json))
    result = nlu.parse("Giữ vé cho tôi", DialogueState())

    assert result.intent == Intent.BOOKING_GUIDANCE
    assert result.patch.quantity == 2
