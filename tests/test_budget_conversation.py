import pytest

from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand
from smartevent_ai.domain.dialogue import DialogueState, Intent, Scope, merge_state


class SearchOnly:
    def __init__(self):
        self.calls = []

    async def execute(self, name, arguments):
        assert name == "search_events"
        self.calls.append(arguments)
        return {"data": [], "result_complete": True}


@pytest.mark.parametrize("answer", ["1 vé", "1ve", "một vé", "moi ve", "mỗi vé", "Tính mỗi vé nhé"])
def test_budget_scope_reply_keeps_original_search(answer: str) -> None:
    state = DialogueState(budget_amount=500_000, active_intent=Intent.SEARCH_EVENT)
    parsed = RuleBasedVietnameseNLU().parse(answer, state)
    updated = merge_state(state, parsed.patch)
    assert not parsed.needs_clarification
    assert parsed.intent is Intent.SEARCH_EVENT
    assert updated.budget_amount == 500_000 and updated.budget_scope is Scope.PER_TICKET


@pytest.mark.asyncio
async def test_screenshot_sequence_never_asks_unusable_budget_scope() -> None:
    tools = SearchOnly()
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    state = DialogueState()
    # Turn 1: budget specified, scope unknown -> clarify
    r1 = await chat.handle(
        ChatCommand(message="Tìm kiếm vé sự kiện dưới 500k trong tháng 11", previous_state=state)
    )
    assert r1.status == "CLARIFY"
    assert "Ngân sách này tính" in r1.answer
    assert r1.state.budget_amount == 500_000
    state = r1.state

    # Turn 2: "1 vé" -> resolves scope to PER_TICKET
    r2 = await chat.handle(ChatCommand(message="1 vé", previous_state=state))
    assert r2.state.quantity == 1 and r2.state.budget_scope is Scope.PER_TICKET
    state = r2.state


@pytest.mark.asyncio
async def test_supported_city_followup_searches_without_claiming_price_match() -> None:
    tools = SearchOnly()
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    first = await chat.handle(ChatCommand(message="Tìm 3 vé ở Hồ Chí Minh dưới 800 nghìn"))
    assert first.status == "CLARIFY"
    reply = await chat.handle(ChatCommand(message="Tính tổng nhé", previous_state=first.state))
    assert reply.state.budget_scope is Scope.TOTAL
    assert len(tools.calls) == 1
    assert tools.calls[0]["city"] == "Hồ Chí Minh"
    assert "maxPrice" in tools.calls[0]


def test_generic_search_phrase_is_not_forwarded_as_keyword() -> None:
    parsed = RuleBasedVietnameseNLU().parse(
        "Tìm kiếm vé sự kiện dưới 500k trong tháng 11", DialogueState()
    )
    assert parsed.patch.search_query is None
