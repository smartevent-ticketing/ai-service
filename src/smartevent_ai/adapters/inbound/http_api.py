"""FastAPI adapter translating HTTP/Pydantic DTOs to pure application models."""

from __future__ import annotations

from uuid import UUID
from datetime import datetime
from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smartevent_ai import __version__
from smartevent_ai.adapters.inbound.request_telemetry import RequestTelemetry
from smartevent_ai.application.models import ChatCommand, ChatResult
from smartevent_ai.domain.dialogue import DialogueState, Intent, Scope
from smartevent_ai.domain.errors import (
    SmartEventError,
    BackendUnavailable,
    ContractViolation,
    ToolUnavailable,
    ModelUnavailable,
    KnowledgeUnavailable,
    UpstreamTimeout,
)
from smartevent_ai.infrastructure.settings import Settings


class DialogueStateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(default=None, min_length=1, max_length=80)
    quantity: int | None = Field(default=None, ge=1, le=20, strict=True)
    budget_amount: int | None = Field(default=None, ge=0, le=1_000_000_000, strict=True)
    budget_scope: Scope = Scope.UNKNOWN
    event_name: str | None = Field(default=None, min_length=1, max_length=120)
    search_query: str | None = Field(default=None, min_length=1, max_length=120)
    active_intent: Intent | None = None
    start_from: datetime | None = None
    start_before: datetime | None = None
    price_comparison: str | None = Field(default=None, pattern="^(LT|LTE)$")
    faq_topic: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("city", "event_name", "search_query")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("state text fields cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_budget_scope(self) -> "DialogueStateDTO":
        if self.budget_amount is None and self.budget_scope is not Scope.UNKNOWN:
            raise ValueError("budget_scope requires budget_amount")
        self.to_domain()
        return self

    def to_domain(self) -> DialogueState:
        return DialogueState(**self.model_dump())

    @classmethod
    def from_domain(cls, state: DialogueState) -> "DialogueStateDTO":
        return cls(**asdict(state))


class ChatRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    previous_state: DialogueStateDTO = Field(default_factory=DialogueStateDTO)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value

    def to_command(self) -> ChatCommand:
        return ChatCommand(
            message=self.message,
            conversation_id=self.conversation_id,
            previous_state=self.previous_state.to_domain(),
        )


class CitationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    version: str
    title: str
    canonical_uri: str
    chunk_id: str
    heading_path: list[str]
    start: int
    end: int


class ChatEventLinkDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)


class EventCardDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    slug: str
    detail_path: str
    city: str | None = None
    venue_name: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    price: str | None = None
    currency: str | None = None
    ticket_type_id: UUID | None = None
    sale_phase_id: UUID | None = None
    price_observed_at: str | None = None
    price_basis: str | None = None


class NavigationActionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(pattern="^(VIEW_EVENT|BROWSE_EVENTS)$")
    route: str = Field(pattern=r"^/events(?:/[a-zA-Z0-9_-]+)?$")
    label: str
    event_id: UUID | None = None


class ChatResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    intent: str
    state: DialogueStateDTO
    answer: str
    grounding: str
    tool_called: str | None = None
    events: list[EventCardDTO] = Field(default_factory=list)
    actions: list[NavigationActionDTO] = Field(default_factory=list)
    has_more: bool = False
    mode: str = "rule"
    status: str = "OK"
    citations: list[CitationDTO] = Field(default_factory=list)
    event_links: list[ChatEventLinkDTO] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: ChatResult) -> "ChatResponseDTO":
        return cls(
            conversation_id=result.conversation_id,
            intent=result.intent.value,
            state=DialogueStateDTO.from_domain(result.state),
            answer=result.answer,
            grounding=result.grounding.value,
            tool_called=result.tool_called,
            events=[EventCardDTO(**asdict(e)) for e in result.events],
            actions=[NavigationActionDTO(**asdict(a)) for a in result.actions],
            has_more=result.has_more,
            mode=result.mode,
            status=result.status,
            event_links=[
                ChatEventLinkDTO(event_id=UUID(e.event_id), title=e.title, slug=e.slug)
                for e in result.event_links
            ],
            citations=[
                CitationDTO(
                    source_id=c.source_id,
                    version=c.version,
                    title=c.title,
                    canonical_uri=c.canonical_uri,
                    chunk_id=c.chunk_id,
                    heading_path=list(c.heading_path),
                    start=c.start,
                    end=c.end,
                )
                for c in result.citations
            ],
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    from smartevent_ai.infrastructure.bootstrap import build_chat

    configuration = settings or Settings()
    chat, gateway = build_chat(configuration)
    app = FastAPI(title="SmartEvent AI Read-only Service", version=__version__)
    app.state.chat = chat
    app.state.gateway = gateway
    app.add_middleware(RequestTelemetry)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        request.state.error_code = "INVALID_REQUEST"
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_REQUEST",
                "message": "Invalid chat request",
                "request_id": request.state.request_id,
                "retryable": False,
            },
        )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> dict[str, object]:
        enabled = gateway.available_names()
        return {
            "status": "ready" if enabled and configuration.nlu_backend == "rule" else "degraded",
            "business_tools_enabled": enabled,
            "model_backend": configuration.nlu_backend,
            "last_nlu_mode": app.state.chat.last_nlu_mode,
            "nlu_availability": "available"
            if configuration.nlu_backend == "rule"
            else "unverified",
            "business_tool_capabilities": gateway.capabilities(),
            "policy_retrieval": {
                "status": app.state.chat.policy_status(),
                "answer_mode": app.state.chat.policy_answer_mode(),
            },
        }

    @app.post("/api/v1/chat", response_model=ChatResponseDTO)
    async def post_chat(body: ChatRequestDTO, request: Request) -> ChatResponseDTO:
        result = await app.state.chat.handle(body.to_command())
        request.state.chat_outcome = {
            "intent": result.intent.value,
            "nlu_mode": result.mode,
            "grounding": result.grounding.value,
            "tool_name": result.tool_called,
            "result_status": result.status,
        }
        return ChatResponseDTO.from_result(result)

    @app.exception_handler(SmartEventError)
    async def domain_error(request: Request, exc: SmartEventError) -> JSONResponse:
        # Do not expose internal backend content, secrets or contract details.
        errors = (
            (UpstreamTimeout, 504, "UPSTREAM_TIMEOUT", True),
            (KnowledgeUnavailable, 503, "KNOWLEDGE_UNAVAILABLE", True),
            (ModelUnavailable, 503, "MODEL_UNAVAILABLE", True),
            (BackendUnavailable, 503, "BACKEND_UNAVAILABLE", True),
            (ContractViolation, 502, "UPSTREAM_CONTRACT_ERROR", False),
            (ToolUnavailable, 503, "TOOL_DISABLED", False),
        )
        status, code, retryable = next(
            (
                (status, code, retryable)
                for kind, status, code, retryable in errors
                if isinstance(exc, kind)
            ),
            (422, "INVALID_REQUEST", False),
        )
        request.state.error_code = code
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": "Request could not be completed",
                "request_id": request.state.request_id,
                "retryable": retryable,
            },
        )

    return app
