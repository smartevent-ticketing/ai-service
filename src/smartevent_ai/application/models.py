"""Application request/result records, independent of HTTP/Pydantic."""

from dataclasses import dataclass
from uuid import UUID

from smartevent_ai.domain.dialogue import DialogueState, Grounding, Intent


@dataclass(frozen=True, slots=True)
class ChatCommand:
    message: str
    conversation_id: UUID | None = None
    previous_state: DialogueState = DialogueState()


@dataclass(frozen=True, slots=True)
class ChatResult:
    conversation_id: UUID
    intent: Intent
    state: DialogueState
    answer: str
    grounding: Grounding
    tool_called: str | None = None
