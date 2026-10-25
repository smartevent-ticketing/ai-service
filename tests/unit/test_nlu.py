import pytest

from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Intent,
    Scope,
    merge_state,
)
from smartevent_ai.domain.search import EventSearchCriteria


def test_extracts_quantity_city_total_budget_and_search_term() -> None:
    nlu = RuleBasedVietnameseNLU()
    result = nlu.parse("Tìm 3 vé concert ở Hà Nội dưới 1,5 triệu tổng", DialogueState())
    assert result.intent == Intent.SEARCH_EVENT
    assert result.patch.quantity == 3 and result.patch.city == "Hà Nội"
    assert result.patch.budget_amount == 1_500_000
    assert result.patch.budget_scope == Scope.TOTAL
    assert result.patch.search_query == "concert"


def test_unknown_budget_scope_needs_clarification() -> None:
    result = RuleBasedVietnameseNLU().parse("3 vé dưới 800 nghìn", DialogueState())
    assert result.intent == Intent.TICKET_RECOMMEND
    assert result.needs_clarification is True
    assert result.clarification_reason == ClarificationReason.BUDGET_SCOPE


def test_scope_only_followup_resolves_previous_ambiguity() -> None:
    previous = DialogueState(quantity=3, budget_amount=800_000, budget_scope=Scope.UNKNOWN)
    result = RuleBasedVietnameseNLU().parse("Tính tổng nhé", previous)
    assert result.intent == Intent.TICKET_RECOMMEND
    assert result.patch.budget_scope == Scope.TOTAL
    assert result.needs_clarification is False


def test_out_of_range_budget_is_clarified_not_raised() -> None:
    result = RuleBasedVietnameseNLU().parse("3 vé dưới 2000 triệu tổng", DialogueState())
    assert result.needs_clarification is True
    assert result.clarification_reason == ClarificationReason.BUDGET_OUT_OF_RANGE
    assert result.patch.budget_amount is None


def test_no_transaction_intent_from_request() -> None:
    result = RuleBasedVietnameseNLU().parse("Giữ vé giúp tôi ngay đi", DialogueState())
    assert result.intent == Intent.BOOKING_GUIDANCE


def test_scope_per_ticket_followup() -> None:
    previous = DialogueState(quantity=2, budget_amount=500_000, budget_scope=Scope.UNKNOWN)
    result = RuleBasedVietnameseNLU().parse("Tính mỗi vé nhé", previous)
    assert result.patch.budget_scope == Scope.PER_TICKET


def test_intent_classification_account_policy_and_greeting() -> None:
    nlu = RuleBasedVietnameseNLU()
    cases = {
        "Tôi muốn hoàn tiền": Intent.REFUND_POLICY,
        "Trạng thái thanh toán": Intent.PAYMENT_STATUS,
        "Đơn hàng của tôi": Intent.ORDER_STATUS,
        "Vé của tôi": Intent.MY_TICKETS,
        "Xin chào": Intent.GREETING,
        "không hiểu": Intent.CLARIFY,
    }
    for text, expected in cases.items():
        assert nlu.parse(text, DialogueState()).intent == expected


def test_bare_show_becomes_search_query() -> None:
    result = RuleBasedVietnameseNLU().parse("show ở Đà Nẵng", DialogueState())
    assert result.intent == Intent.SEARCH_EVENT
    assert result.patch.search_query == "show"
    assert result.patch.city == "Đà Nẵng"


@pytest.mark.parametrize(
    "message,city",
    [
        ("ở Đà Nẵng", "Đà Nẵng"),
        ("chuyển sang Đà Nẵng", "Đà Nẵng"),
        ("tìm ở Đà Nẵng", "Đà Nẵng"),
        ("tìm sự kiện tại Đà Nẵng nhé", "Đà Nẵng"),
        ("Hồ Chí Minh", "Hồ Chí Minh"),
        ("bỏ thành phố", None),
        ("bỏ bộ lọc thành phố Hà Nội", None),
        ("không giới hạn thành phố", None),
    ],
)
def test_city_filter_followup_preserves_search(message, city) -> None:
    nlu = RuleBasedVietnameseNLU()
    previous = merge_state(
        DialogueState(), nlu.parse("Tìm concert ở Hà Nội", DialogueState()).patch
    )
    result = nlu.parse(message, previous)
    current = merge_state(previous, result.patch)
    assert result.intent is Intent.SEARCH_EVENT
    assert current.search_query == "concert"
    assert current.city == city


@pytest.mark.parametrize(
    "message,intent,query",
    [
        ("Tìm triển lãm tại Đà Nẵng", Intent.SEARCH_EVENT, "triển lãm"),
        ("Tìm tất cả sự kiện", Intent.SEARCH_EVENT, None),
        ("Xem đơn hàng của tôi ở Đà Nẵng", Intent.ORDER_STATUS, "concert"),
        ("Xin chào Đà Nẵng", Intent.GREETING, "concert"),
        ("Thời tiết Đà Nẵng", Intent.CLARIFY, "concert"),
        ("Bắt đầu lại", Intent.CLARIFY, None),
    ],
)
def test_filter_continuation_does_not_override_new_task_or_clear(message, intent, query) -> None:
    nlu = RuleBasedVietnameseNLU()
    previous = DialogueState(
        city="Hà Nội", search_query="concert", active_intent=Intent.SEARCH_EVENT
    )
    result = nlu.parse(message, previous)
    assert result.intent is intent
    assert merge_state(previous, result.patch).search_query == query


def test_city_filter_resumes_ticket_preferences_without_turning_into_search() -> None:
    previous = DialogueState(quantity=2, active_intent=Intent.TICKET_RECOMMEND)
    result = RuleBasedVietnameseNLU().parse("ở Đà Nẵng", previous)
    assert result.intent is Intent.TICKET_RECOMMEND
    assert merge_state(previous, result.patch).quantity == 2


@pytest.mark.parametrize(
    "message,quantity,query,city",
    [
        ("Tìm 2 vé ở Hà Nội", 2, None, "Hà Nội"),
        ("Tìm 2 ghế ở Đà Nẵng", 2, None, "Đà Nẵng"),
        ("Tìm 1 vé", 1, None, None),
        ("Tìm 20 ghế", 20, None, None),
        ("Tìm 2vé ở Hà Nội", 2, None, "Hà Nội"),
        ("Tìm concert 3 vé dưới 800 nghìn tổng", 3, "concert", None),
        ("Tìm 3 vé concert ở Hà Nội", 3, "concert", "Hà Nội"),
        ("Tìm sự kiện 2 vé concert", 2, "concert", None),
        ("Tìm concert 2 vé mùa hè", 2, "concert mùa hè", None),
        ("Tìm concert 2026 ở Hà Nội", None, "concert 2026", "Hà Nội"),
        ("Tìm show 20", None, "show 20", None),
        ("Tìm 2 vé concert 2026 ở Hà Nội", 2, "concert 2026", "Hà Nội"),
    ],
)
def test_search_arguments_separate_ticket_quantity_from_title(message, quantity, query, city):
    previous = DialogueState(search_query="old query", active_intent=Intent.SEARCH_EVENT)
    result = RuleBasedVietnameseNLU().parse(message, previous)
    state = merge_state(previous, result.patch)
    assert result.intent is Intent.SEARCH_EVENT
    assert not result.needs_clarification
    assert state.quantity == quantity
    assert state.search_query == query
    expected = {"page": 0, "size": 10}
    if query is not None:
        expected["q"] = query
    if city is not None:
        expected["city"] = city
    assert EventSearchCriteria.from_state(state).as_tool_arguments() == expected


@pytest.mark.parametrize("quantity", ["0", "21", "-2", "1,5"])
def test_search_invalid_quantity_requires_clarification(quantity):
    result = RuleBasedVietnameseNLU().parse(f"Tìm concert {quantity} vé", DialogueState())
    assert result.needs_clarification
    assert result.clarification_reason is ClarificationReason.QUANTITY_OUT_OF_RANGE
    assert result.patch.search_query is None


def test_budget_scope_followup_preserves_search_without_quantity_in_query():
    nlu = RuleBasedVietnameseNLU()
    first = nlu.parse("Tìm concert 3 vé ở Hà Nội dưới 800 nghìn", DialogueState())
    assert first.clarification_reason is ClarificationReason.BUDGET_SCOPE
    previous = merge_state(DialogueState(), first.patch)
    followup = nlu.parse("Tính tổng nhé", previous)
    state = merge_state(previous, followup.patch)
    assert followup.intent is Intent.SEARCH_EVENT
    assert not followup.needs_clarification
    assert state.quantity == 3
    assert state.budget_amount == 800_000
    assert state.budget_scope is Scope.TOTAL
    assert EventSearchCriteria.from_state(state).as_tool_arguments() == {
        "q": "concert",
        "city": "Hà Nội",
        "page": 0,
        "size": 10,
    }
