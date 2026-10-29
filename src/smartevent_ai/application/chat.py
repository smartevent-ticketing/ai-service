"""Chat orchestration use case with inward-facing dependencies only."""

from dataclasses import replace
from uuid import UUID, uuid4

from smartevent_ai.application.models import ChatCommand, ChatEventLink, ChatResult
from smartevent_ai.application.ports import BusinessReadTools, LanguageUnderstanding
from smartevent_ai.application.knowledge_ports import PolicyReader
from smartevent_ai.application.response_composer import ResponseComposer
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Grounding,
    Intent,
    merge_state,
)
from smartevent_ai.domain.errors import SmartEventError
from smartevent_ai.domain.search import EventSearchCriteria


class ChatUseCase:
    def __init__(
        self,
        nlu: LanguageUnderstanding,
        tools: BusinessReadTools,
        composer: ResponseComposer | None = None,
        policies: PolicyReader | None = None,
    ) -> None:
        self._nlu = nlu
        self._tools = tools
        self._composer = composer or ResponseComposer()
        self._policies = policies

    def policy_status(self) -> str:
        return self._policies.status() if self._policies is not None else "disabled"

    async def handle(self, request: ChatCommand) -> ChatResult:
        understood = self._nlu.parse(request.message, request.previous_state)
        state = merge_state(request.previous_state, understood.patch)
        conversation_id = request.conversation_id or uuid4()

        if (
            understood.needs_clarification
            and understood.clarification_reason is not ClarificationReason.BUDGET_SCOPE
        ):
            return ChatResult(
                conversation_id=conversation_id,
                intent=understood.intent,
                state=state,
                answer=self._composer.clarification(understood.clarification_reason),
                grounding=Grounding.NO_LIVE_DATA,
            )

        # Price/inventory tools are not enabled. Do not ask a question that leads
        # users into an unavailable recommendation workflow.
        if (
            understood.intent in (Intent.SEARCH_EVENT, Intent.TICKET_RECOMMEND)
            and state.budget_amount is not None
        ):
            note = (
                "Hiện tôi chưa lọc được sự kiện theo giá vé hoặc tháng, nên chưa thể "
                "xác nhận sự kiện nào đáp ứng ngân sách của bạn. "
            )
            if state.city or state.search_query:
                result = await self._search_events(conversation_id, Intent.SEARCH_EVENT, state)
                return replace(
                    result,
                    answer=note
                    + "Danh sách dưới đây mới áp dụng thành phố/từ khóa, chưa áp dụng ngân sách hoặc tháng.\n"
                    + result.answer,
                )
            return ChatResult(
                conversation_id=conversation_id,
                intent=understood.intent,
                state=state,
                answer=note
                + "Tôi có thể tìm theo thành phố hoặc từ khóa. Bạn muốn xem sự kiện ở thành phố nào?",
                grounding=Grounding.NO_LIVE_DATA,
            )

        if understood.intent is Intent.SEARCH_EVENT:
            result = await self._search_events(conversation_id, understood.intent, state)
            if result.grounding is Grounding.BACKEND_READ and any(
                marker in request.message.casefold()
                for marker in (
                    "tháng",
                    "tuần",
                    "hôm nay",
                    "ngày mai",
                    "ngày kia",
                    "năm nay",
                )
            ):
                # The backend search contract has no date arguments. Never imply they were used.
                result = replace(
                    result,
                    answer=(
                        "Hiện tôi chưa lọc được theo khoảng ngày bạn yêu cầu. "
                        "Dưới đây là kết quả theo thành phố/từ khóa; hãy kiểm tra ngày diễn ra.\n"
                        + result.answer
                    ),
                )
            return result

        if (
            understood.intent in (Intent.REFUND_POLICY, Intent.PUBLIC_HELP)
            and self._policies is not None
        ):
            evidence = await self._policies.answer(request.message)
            if evidence.citations:
                return ChatResult(
                    conversation_id,
                    understood.intent,
                    state,
                    evidence.answer,
                    Grounding.APPROVED_CORPUS,
                    citations=evidence.citations,
                )

        return ChatResult(
            conversation_id=conversation_id,
            intent=understood.intent,
            state=state,
            answer=self._composer.static_answer(understood.intent),
            grounding=Grounding.NO_LIVE_DATA,
        )

    async def _search_events(
        self,
        conversation_id: UUID,
        intent: Intent,
        state: DialogueState,
    ) -> ChatResult:
        criteria = EventSearchCriteria.from_state(state)
        try:
            result = await self._tools.execute("search_events", criteria.as_tool_arguments())
        except SmartEventError:
            return ChatResult(
                conversation_id=conversation_id,
                intent=intent,
                state=state,
                answer=(
                    "Chưa thể xác minh danh sách sự kiện lúc này. "
                    "Bạn vui lòng thử lại sau hoặc mở mục Sự kiện trên SmartEvent."
                ),
                grounding=Grounding.NO_LIVE_DATA,
            )
        return ChatResult(
            conversation_id=conversation_id,
            intent=intent,
            state=state,
            answer=self._composer.search_result(result),
            grounding=Grounding.BACKEND_READ,
            tool_called="search_events",
            event_links=tuple(
                ChatEventLink(event_id=row["id"], title=row["name"], slug=row["slug"])
                for row in result["data"][:10]
            ),
        )
