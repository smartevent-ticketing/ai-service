"""Unit tests for PeftTransformerNLU adapter following TDD."""

from __future__ import annotations

import json


from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Intent,
    Scope,
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


def test_peft_nlu_parses_budget_and_case_insensitive_intent() -> None:
    fake_json = json.dumps(
        {
            "primary_intent": "ticket_recommend",
            "entities": {
                "budget_amount": 700000,
                "budget_scope": "PER_TICKET",
                "city": "Đà Nẵng",
            },
        }
    )
    nlu = PeftTransformerNLU(generator=FakeGenerator(fake_json))
    result = nlu.parse("Tìm vé 700k mỗi vé ở Đà Nẵng", DialogueState())

    assert result.intent == Intent.TICKET_RECOMMEND
    assert result.patch.budget_amount == 700000
    assert result.patch.budget_scope == Scope.PER_TICKET
    assert result.patch.active_intent == Intent.TICKET_RECOMMEND


def test_peft_nlu_budget_out_of_range_clarifies() -> None:
    fake_json = json.dumps(
        {
            "primary_intent": "TICKET_RECOMMEND",
            "entities": {
                "budget_amount": 3_000_000_000,
            },
        }
    )
    nlu = PeftTransformerNLU(generator=FakeGenerator(fake_json))
    result = nlu.parse("Vé dưới 3 tỷ", DialogueState())

    assert result.needs_clarification is True
    assert result.clarification_reason == ClarificationReason.BUDGET_OUT_OF_RANGE


def test_peft_nlu_missing_adapter_path_raises_on_load(tmp_path) -> None:
    import pytest

    missing_nlu = PeftTransformerNLU(adapter_path=tmp_path / "nonexistent")
    with pytest.raises(FileNotFoundError):
        missing_nlu._ensure_loaded()


def test_peft_nlu_resolves_budget_scope_with_previous_state() -> None:
    fake_json = json.dumps(
        {
            "primary_intent": "TICKET_RECOMMEND",
            "entities": {"budget_scope": "PER_TICKET"},
        }
    )
    fake_gen = FakeGenerator(fake_json)
    nlu = PeftTransformerNLU(generator=fake_gen)
    prev_state = DialogueState(
        active_intent=Intent.TICKET_RECOMMEND,
        city="Đà Nẵng",
        quantity=1,
        budget_amount=300_000,
        event_name="EDM Night",
    )
    result = nlu.parse("mỗi vé", prev_state)

    assert fake_gen.last_prompt is not None
    assert "Trạng thái trước:" in fake_gen.last_prompt
    assert "active_intent: TICKET_RECOMMEND" in fake_gen.last_prompt
    assert "city: Đà Nẵng" in fake_gen.last_prompt
    assert "budget_amount: 300000" in fake_gen.last_prompt
    assert "event_name: EDM Night" in fake_gen.last_prompt
    assert result.patch.budget_scope == Scope.PER_TICKET
