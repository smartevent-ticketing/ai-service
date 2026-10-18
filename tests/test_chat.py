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
