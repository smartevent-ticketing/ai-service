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
    for text in ("Tìm kiếm vé sự kiện dưới 500k trong tháng 11", "1 vé", "mỗi vé", "Là sao"):
        reply = await chat.handle(ChatCommand(message=text, previous_state=state))
        assert "chưa lọc được" in reply.answer
        assert "Ngân sách này tính" not in reply.answer
        assert "chưa có tồn kho" not in reply.answer
        assert reply.state.budget_amount == 500_000
        state = reply.state
    assert not tools.calls
    assert state.quantity == 1 and state.budget_scope is Scope.PER_TICKET


@pytest.mark.asyncio
async def test_supported_city_followup_searches_without_claiming_price_match() -> None:
    tools = SearchOnly()
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    first = await chat.handle(ChatCommand(message="3 vé dưới 800 nghìn"))
    reply = await chat.handle(ChatCommand(message="Ở Hồ Chí Minh", previous_state=first.state))
    assert tools.calls == [{"page": 0, "size": 10, "city": "Hồ Chí Minh"}]
    assert "chưa áp dụng ngân sách" in reply.answer


def test_generic_search_phrase_is_not_forwarded_as_keyword() -> None:
    parsed = RuleBasedVietnameseNLU().parse(
        "Tìm kiếm vé sự kiện dưới 500k trong tháng 11", DialogueState()
    )
    assert parsed.patch.search_query is None
