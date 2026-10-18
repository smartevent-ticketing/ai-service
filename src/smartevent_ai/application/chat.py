"""Chat orchestration use case with inward-facing dependencies only."""

from uuid import UUID, uuid4

from smartevent_ai.application.models import ChatCommand, ChatResult
from smartevent_ai.application.ports import BusinessReadTools, LanguageUnderstanding
from smartevent_ai.application.response_composer import ResponseComposer
from smartevent_ai.domain.dialogue import DialogueState, Grounding, Intent, merge_state
from smartevent_ai.domain.errors import SmartEventError
from smartevent_ai.domain.search import EventSearchCriteria


class ChatUseCase:
    def __init__(
        self,
        nlu: LanguageUnderstanding,
        tools: BusinessReadTools,
        composer: ResponseComposer | None = None,
    ) -> None:
        self._nlu = nlu
        self._tools = tools
        self._composer = composer or ResponseComposer()

    async def handle(self, request: ChatCommand) -> ChatResult:
        understood = self._nlu.parse(request.message, request.previous_state)
        state = merge_state(request.previous_state, understood.patch)
        conversation_id = request.conversation_id or uuid4()

        if understood.needs_clarification:
            return ChatResult(
                conversation_id=conversation_id,
                intent=understood.intent,
                state=state,
                answer=self._composer.clarification(understood.clarification_reason),
                grounding=Grounding.NO_LIVE_DATA,
            )

        if understood.intent is Intent.SEARCH_EVENT:
            return await self._search_events(conversation_id, understood.intent, state)

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
                    "Chưa thể xác minh danh sách sự kiện từ backend; "
                    "chức năng đọc dữ liệu chưa được nghiệm thu."
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
        )
