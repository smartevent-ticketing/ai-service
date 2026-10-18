"""FastAPI adapter translating HTTP/Pydantic DTOs to pure application models."""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smartevent_ai import __version__
from smartevent_ai.adapters.inbound.request_telemetry import RequestTelemetry
from smartevent_ai.application.models import ChatCommand, ChatResult
from smartevent_ai.domain.dialogue import DialogueState, Intent, Scope
from smartevent_ai.domain.errors import SmartEventError
from smartevent_ai.infrastructure.bootstrap import build_chat
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
        return self

    def to_domain(self) -> DialogueState:
        return DialogueState(
            city=self.city,
            quantity=self.quantity,
            budget_amount=self.budget_amount,
            budget_scope=self.budget_scope,
            event_name=self.event_name,
            search_query=self.search_query,
            active_intent=self.active_intent,
        )

    @classmethod
    def from_domain(cls, state: DialogueState) -> "DialogueStateDTO":
        return cls(
            city=state.city,
            quantity=state.quantity,
            budget_amount=state.budget_amount,
            budget_scope=state.budget_scope,
            event_name=state.event_name,
            search_query=state.search_query,
            active_intent=state.active_intent,
        )


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


class ChatResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    intent: str
    state: DialogueStateDTO
    answer: str
    grounding: str
    tool_called: str | None = None
    citations: list[CitationDTO] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: ChatResult) -> "ChatResponseDTO":
        return cls(
            conversation_id=result.conversation_id,
            intent=result.intent.value,
            state=DialogueStateDTO.from_domain(result.state),
            answer=result.answer,
            grounding=result.grounding.value,
            tool_called=result.tool_called,
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
    configuration = settings or Settings()
    chat, gateway = build_chat(configuration)
    app = FastAPI(title="SmartEvent AI Read-only Service", version=__version__)
    app.add_middleware(RequestTelemetry)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> dict[str, object]:
        enabled = gateway.available_names()
        return {
            "status": "degraded" if not enabled else "ready",
            "business_tools_enabled": enabled,
            "model_backend": "rule_based_baseline_only",
            "policy_retrieval": {"status": chat.policy_status(), "answer_mode": "extractive"},
        }

    @app.post("/api/v1/chat", response_model=ChatResponseDTO)
    async def post_chat(body: ChatRequestDTO) -> ChatResponseDTO:
        return ChatResponseDTO.from_result(await chat.handle(body.to_command()))

    @app.exception_handler(SmartEventError)
    async def domain_error(request: Request, exc: SmartEventError) -> JSONResponse:
        # Do not expose internal backend content, secrets or contract details.
        return JSONResponse(
            status_code=422,
            content={
                "code": exc.__class__.__name__,
                "message": "Request could not be completed",
            },
        )

    return app


app = create_app()
