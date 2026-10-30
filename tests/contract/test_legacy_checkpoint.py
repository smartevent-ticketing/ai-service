import json
from datetime import datetime, timezone

import pytest

from smartevent_ai.adapters.outbound.legacy_checkpoint import adapt_checkpoint
from smartevent_ai.adapters.outbound.model_understanding import parse_model_understanding
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import DialogueState, Intent, Scope, merge_state

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def test_original_checkpoint_fields_are_adapted_without_retraining_or_guessing_scope():
    raw = '{"entities":{"city":"Hồ Chí Minh","budget_currency":"VND"},"entities":{},"primary_intent":"SEARCH_EVENT","state_delta":[{"operation":"SET","slot":"budget_amount","value":500000},{"operation":"SET","slot":"month","value":"tháng 11"}]}'
    state = DialogueState()
    payload = adapt_checkpoint(
        raw,
        "Tìm sự kiện ở Hồ Chí Minh dưới 500k trong tháng 11",
        state,
        RuleBasedVietnameseNLU(lambda: NOW),
    )
    result = parse_model_understanding(payload, state)
    merged = merge_state(state, result.patch)
    assert merged.city == "Hồ Chí Minh" and merged.budget_amount == 500000
    assert merged.budget_scope is Scope.UNKNOWN and result.needs_clarification
    assert merged.start_from.month == 11 and merged.start_before.month == 12
    assert merged.price_comparison == "LT"


@pytest.mark.parametrize(
    "bad", ["city", "month", "currency", "duplicate_route", "duplicate_entities", "budget", "date"]
)
def test_compatibility_does_not_approve_conflicting_or_unsupported_conditions(bad):
    payload = {
        "primary_intent": "SEARCH_EVENT",
        "entities": {"city": "Hồ Chí Minh"},
        "state_delta": [],
    }
    if bad == "city":
        payload["state_delta"] = [{"op": "SET", "slot": "city", "value": "Hà Nội"}]
    elif bad == "month":
        payload["entities"]["month"] = "tháng 10"
    elif bad == "currency":
        payload["entities"]["budget_currency"] = "USD"
    elif bad == "budget":
        payload["entities"]["budget_amount"] = 499999
    elif bad == "date":
        payload["state_delta"] = [
            {"op": "SET", "slot": "start_from", "value": "2026-10-01T00:00:00+07:00"}
        ]
    raw = json.dumps(payload)
    if bad == "duplicate_route":
        raw = '{"primary_intent":"SEARCH_EVENT","primary_intent":"PUBLIC_HELP"}'
    elif bad == "duplicate_entities":
        raw = '{"entities":{"city":"Hồ Chí Minh"},"entities":{"city":"Hà Nội"}}'
    with pytest.raises(ValueError):
        adapt_checkpoint(
            raw,
            "Tìm sự kiện ở Hồ Chí Minh dưới 500k tháng 11",
            DialogueState(),
            RuleBasedVietnameseNLU(lambda: NOW),
        )


def test_legacy_payment_help_alias_still_uses_approved_public_help_route():
    payload = adapt_checkpoint(
        '{"primary_intent":"TOOLBAR_PAYMENT_METHOD"}',
        "Có những cách thanh toán nào",
        DialogueState(),
        RuleBasedVietnameseNLU(lambda: NOW),
    )
    result = parse_model_understanding(payload, DialogueState())
    assert result.intent is Intent.PUBLIC_HELP
