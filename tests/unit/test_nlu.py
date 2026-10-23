from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Intent,
    Scope,
)


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
