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
async def test_time_request_is_not_presented_as_an_applied_backend_filter() -> None:
    result = await ChatUseCase(RuleBasedVietnameseNLU(), RecordingTools()).handle(
        ChatCommand(message="Có sự kiện gì cuối tháng này ở Hồ Chí Minh?")
    )
    assert "chưa lọc được theo khoảng ngày" in result.answer


@pytest.mark.asyncio
async def test_event_links_come_from_projected_backend_rows() -> None:
    class EventTools:
        async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "data": [
                    {
                        "id": "08c25afc-f9c9-4db0-aab7-02c779779d6c",
                        "name": "Đêm nhạc",
                        "slug": "dem-nhac",
                    }
                ]
            }

    result = await ChatUseCase(RuleBasedVietnameseNLU(), EventTools()).handle(
        ChatCommand(message="Tìm sự kiện ở Hồ Chí Minh")
    )
    assert len(result.event_links) == 1
    assert result.event_links[0].slug == "dem-nhac"
    assert result.event_links[0].title == "Đêm nhạc"
    from smartevent_ai.adapters.inbound.http_api import ChatResponseDTO

    payload = ChatResponseDTO.from_result(result).model_dump(mode="json")
    assert payload["event_links"][0] == {
        "event_id": "08c25afc-f9c9-4db0-aab7-02c779779d6c",
        "title": "Đêm nhạc",
        "slug": "dem-nhac",
    }


@pytest.mark.asyncio
async def test_non_search_answer_has_no_event_links() -> None:
    result = await ChatUseCase(RuleBasedVietnameseNLU(), RecordingTools()).handle(
        ChatCommand(message="Giữ vé giúp tôi")
    )
    assert result.event_links == ()
