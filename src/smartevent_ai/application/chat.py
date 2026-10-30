"""Chat orchestration use case with inward-facing dependencies only."""

import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

from smartevent_ai.application.models import (
    ChatCommand,
    ChatEventLink,
    ChatResult,
    EventCard,
    NavigationAction,
)
from smartevent_ai.application.ports import (
    BusinessReadTools,
    LanguageUnderstanding,
    WarmableLanguageUnderstanding,
    ModelRuntime,
)
from smartevent_ai.application.knowledge_ports import PolicyReader
from smartevent_ai.application.response_composer import ResponseComposer
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
    DialogueState,
    Grounding,
    Intent,
    merge_state,
    ClearGroup,
)
from smartevent_ai.domain.errors import (
    ContractViolation,
    ToolUnavailable,
    UpstreamTimeout,
    ModelUnavailable,
)
from smartevent_ai.domain.search import EventSearchCriteria


class ChatUseCase:
    def __init__(
        self,
        nlu: LanguageUnderstanding,
        tools: BusinessReadTools,
        composer: ResponseComposer | None = None,
        policies: PolicyReader | None = None,
        nlu_timeout_seconds: float = 12.0,
        model_runtime: ModelRuntime | None = None,
    ) -> None:
        self._nlu = nlu
        self._tools = tools
        self._composer = composer or ResponseComposer()
        self._policies = policies
        self.last_nlu_mode = "not_probed"
        self._nlu_timeout_seconds = nlu_timeout_seconds
        self._model_runtime = model_runtime

    def model_runtime_status(self) -> dict[str, object]:
        return self._model_runtime.status() if self._model_runtime else {"mode": "independent"}

    def close_models(self) -> None:
        if self._model_runtime:
            self._model_runtime.close()

    def warmup_nlu(self) -> None:
        """Exercise the configured provider outside the per-request deadline."""
        self.last_nlu_mode = "unavailable"
        if not isinstance(self._nlu, WarmableLanguageUnderstanding):
            raise ModelUnavailable("Configured NLU does not support startup warmup")
        result = self._nlu.warmup()
        if result.mode != "model":
            raise ModelUnavailable("NLU startup warmup returned fallback")
        self.last_nlu_mode = result.mode

    def policy_status(self) -> str:
        return self._policies.status() if self._policies is not None else "disabled"

    def policy_answer_mode(self) -> str:
        if self._policies is None:
            return "extractive"
        return getattr(self._policies, "answer_mode", "extractive")

    async def handle(self, request: ChatCommand) -> ChatResult:
        try:
            understood = await asyncio.wait_for(
                asyncio.to_thread(self._nlu.parse, request.message, request.previous_state),
                timeout=self._nlu_timeout_seconds,
            )
        except TimeoutError as exc:
            self.last_nlu_mode = "unavailable"
            raise UpstreamTimeout("NLU deadline exceeded") from exc
        from smartevent_ai.domain.dialogue import Understanding, Scope

        if not isinstance(understood, Understanding):
            raise ContractViolation("NLU returned invalid output")
        self.last_nlu_mode = understood.mode
        public_intents = (
            Intent.POLICY_FAQ,
            Intent.PUBLIC_HELP,
            Intent.REFUND_POLICY,
            Intent.BOOKING_GUIDANCE,
        )
        if (
            request.previous_state.active_intent in public_intents
            and understood.intent is Intent.SEARCH_EVENT
        ):
            understood = replace(
                understood, patch=replace(understood.patch, clear_group=ClearGroup.ALL_SLOTS)
            )
        state = merge_state(request.previous_state, understood.patch)
        if state.budget_amount is None and understood.clarification_reason in (
            ClarificationReason.BUDGET_SCOPE,
            ClarificationReason.QUANTITY_REQUIRED,
        ):
            understood = replace(understood, needs_clarification=False, clarification_reason=None)
        if understood.intent is Intent.SEARCH_EVENT and state.budget_amount is not None:
            reason = (
                ClarificationReason.BUDGET_SCOPE
                if state.budget_scope is Scope.UNKNOWN
                else ClarificationReason.QUANTITY_REQUIRED
                if state.budget_scope is Scope.TOTAL and state.quantity is None
                else None
            )
            if reason:
                understood = replace(
                    understood, needs_clarification=True, clarification_reason=reason
                )
        conversation_id = request.conversation_id or uuid4()

        if understood.needs_clarification:
            return ChatResult(
                conversation_id=conversation_id,
                intent=understood.intent,
                state=state,
                answer=self._composer.clarification(understood.clarification_reason),
                mode=understood.mode,
                status="CLARIFY",
                grounding=Grounding.NO_LIVE_DATA,
            )

        if understood.intent is Intent.SEARCH_EVENT:
            result = await self._search_events(conversation_id, understood.intent, state)
            return replace(result, mode=understood.mode)

        if understood.intent is Intent.BOOKING_GUIDANCE and not any(
            word in request.message.casefold() for word in ("hướng dẫn", "cách")
        ):
            return ChatResult(
                conversation_id,
                understood.intent,
                state,
                self._composer.static_answer(understood.intent),
                Grounding.NO_LIVE_DATA,
                mode=understood.mode,
                actions=(NavigationAction("BROWSE_EVENTS", "/events", "Xem sự kiện"),),
            )

        if (
            understood.intent
            in (
                Intent.REFUND_POLICY,
                Intent.POLICY_FAQ,
                Intent.BOOKING_GUIDANCE,
                getattr(Intent, "PUBLIC_HELP", Intent.REFUND_POLICY),
            )
            and self._policies is not None
        ):
            query = request.message
            if (
                request.previous_state.active_intent in public_intents
                and request.previous_state.faq_topic
                and query.casefold().strip().startswith(("còn ", "con "))
            ):
                query = request.previous_state.faq_topic + ": " + query
            evidence = await self._policies.answer(query)
            if evidence.citations:
                return ChatResult(
                    conversation_id,
                    understood.intent,
                    state,
                    evidence.answer,
                    Grounding.APPROVED_CORPUS,
                    citations=evidence.citations,
                    mode=evidence.mode,
                )

            return ChatResult(
                conversation_id,
                understood.intent,
                state,
                evidence.answer,
                Grounding.NO_LIVE_DATA,
                mode=evidence.mode,
                status="INSUFFICIENT_EVIDENCE",
            )

        return ChatResult(
            conversation_id=conversation_id,
            intent=understood.intent,
            state=state,
            answer=self._composer.static_answer(understood.intent),
            mode=understood.mode,
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
            # Explicit single business-tool call. The other 13 registry tools,
            # pure_operations (retrieve_policy, optimize_ticket_selection) and
            # ui_actions have no runtime caller; see test_unused_tools_locked.py.
            result = await self._tools.execute("search_events", criteria.as_tool_arguments())
        except ToolUnavailable:
            return ChatResult(
                conversation_id=conversation_id,
                intent=intent,
                state=state,
                answer=(
                    "Chưa thể xác minh danh sách sự kiện lúc này. "
                    "Bạn vui lòng thử lại sau hoặc mở mục Sự kiện trên SmartEvent."
                ),
                grounding=Grounding.NO_LIVE_DATA,
                status="TOOL_DISABLED",
            )
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ContractViolation("Search projection must contain a data list")
        for flag in ("has_more", "pagination_limited", "capped_by_adapter"):
            if flag in result and type(result[flag]) is not bool:
                raise ContractViolation("Invalid search pagination flag")
        events = tuple(EventCard.from_projection(row) for row in result["data"])
        return ChatResult(
            conversation_id=conversation_id,
            intent=intent,
            state=state,
            events=events,
            actions=tuple(
                NavigationAction("VIEW_EVENT", e.detail_path, "Xem chi tiết", e.id) for e in events
            ),
            has_more=bool(
                result.get("has_more")
                or result.get("pagination_limited")
                or result.get("capped_by_adapter")
            ),
            status="OK" if events else "EMPTY",
            answer=self._composer.search_result(result),
            grounding=Grounding.BACKEND_READ,
            tool_called="search_events",
            event_links=tuple(
                ChatEventLink(event_id=str(e.id), title=e.name, slug=e.slug) for e in events[:10]
            ),
        )
