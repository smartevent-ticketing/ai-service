from typing import Any

import pytest

from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand
from smartevent_ai.domain.dialogue import DialogueState, Scope


class RecordingTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {
            "data": [],
            "has_more": False,
            "pagination_limited": False,
            "capped_by_adapter": False,
        }


@pytest.mark.asyncio
async def test_search_uses_structured_filters_not_raw_user_sentence() -> None:
    tools = RecordingTools()
    use_case = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    await use_case.handle(ChatCommand(message="Tìm concert ở Hà Nội"))
    assert tools.calls == [
        ("search_events", {"q": "concert", "city": "Hà Nội", "page": 0, "size": 10})
    ]


@pytest.mark.asyncio
async def test_clarification_followup_preserves_previous_preferences() -> None:
    tools = RecordingTools()
    use_case = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    result = await use_case.handle(
        ChatCommand(
            message="Tính tổng nhé",
            previous_state=DialogueState(
                quantity=3,
                budget_amount=800_000,
                budget_scope=Scope.UNKNOWN,
            ),
        )
    )
    assert result.state.quantity == 3
    assert result.state.budget_amount == 800_000
    assert result.state.budget_scope is Scope.TOTAL


@pytest.mark.asyncio
@pytest.mark.parametrize("message,city", [("ở Đà Nẵng", "Đà Nẵng"), ("bỏ thành phố", None)])
async def test_city_followup_executes_search_with_preserved_query(message, city) -> None:
    tools = RecordingTools()
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    first = await chat.handle(ChatCommand("Tìm concert ở Hà Nội"))
    result = await chat.handle(ChatCommand(message, previous_state=first.state))
    expected = {"q": "concert", "page": 0, "size": 10}
    if city is not None:
        expected["city"] = city
    assert tools.calls[-1] == ("search_events", expected)
    assert result.state.search_query == "concert"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,quantity,arguments",
    [
        ("Tìm 2 vé ở Hà Nội", 2, {"city": "Hà Nội", "page": 0, "size": 10}),
        ("Tìm 20 ghế ở Đà Nẵng", 20, {"city": "Đà Nẵng", "page": 0, "size": 10}),
        (
            "Tìm concert 3 vé dưới 800 nghìn tổng",
            3,
            {"q": "concert", "page": 0, "size": 10},
        ),
        (
            "Tìm concert 2026 2 vé ở Hà Nội",
            2,
            {"q": "concert 2026", "city": "Hà Nội", "page": 0, "size": 10},
        ),
    ],
)
async def test_search_gateway_receives_title_without_ticket_quantity(message, quantity, arguments):
    tools = RecordingTools()
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    result = await chat.handle(ChatCommand(message))
    assert tools.calls == [("search_events", arguments)]
    assert result.state.quantity == quantity


@pytest.mark.asyncio
async def test_search_waits_for_budget_scope_then_sends_clean_query():
    tools = RecordingTools()
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools)
    first = await chat.handle(ChatCommand("Tìm concert 3 vé ở Hà Nội dưới 800 nghìn"))
    assert tools.calls == []
    result = await chat.handle(ChatCommand("Tính tổng nhé", previous_state=first.state))
    assert tools.calls == [
        ("search_events", {"q": "concert", "city": "Hà Nội", "page": 0, "size": 10})
    ]
    assert result.state.quantity == 3
    assert result.state.budget_scope is Scope.TOTAL
