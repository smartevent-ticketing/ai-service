"""Application request/result records, independent of HTTP/Pydantic."""

from dataclasses import dataclass
from uuid import UUID
from decimal import Decimal
import re
from typing import Any

from smartevent_ai.domain.dialogue import DialogueState, Grounding, Intent
from smartevent_ai.domain.knowledge import Citation


@dataclass(frozen=True, slots=True)
class ChatCommand:
    message: str
    conversation_id: UUID | None = None
    previous_state: DialogueState = DialogueState()


@dataclass(frozen=True, slots=True)
class EventCard:
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

    @classmethod
    def from_projection(cls, row: dict[str, Any]) -> "EventCard":
        slug = row["slug"]
        if not isinstance(slug, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,254}", slug):
            raise ValueError("unsafe event slug")
        price = row.get("price")
        if price is not None:
            if row.get("currency") != "VND" or not all(
                row.get(k) for k in ("ticketTypeId", "salePhaseId", "priceObservedAt", "priceBasis")
            ):
                raise ValueError("price evidence is incomplete")
            number = Decimal(str(price))
            if not number.is_finite() or number < 0:
                raise ValueError("invalid price")
            price = format(number, "f")
        return cls(
            UUID(row["id"]),
            row["name"],
            slug,
            f"/events/{slug}",
            row.get("city"),
            row.get("venueName"),
            row.get("startTime"),
            row.get("endTime"),
            price,
            row.get("currency"),
            UUID(row["ticketTypeId"]) if price is not None else None,
            UUID(row["salePhaseId"]) if price is not None else None,
            row.get("priceObservedAt"),
            row.get("priceBasis"),
        )


@dataclass(frozen=True, slots=True)
class NavigationAction:
    type: str
    route: str
    label: str
    event_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    conversation_id: UUID
    intent: Intent
    state: DialogueState
    answer: str
    grounding: Grounding
    tool_called: str | None = None
    citations: tuple[Citation, ...] = ()
    events: tuple[EventCard, ...] = ()
    actions: tuple[NavigationAction, ...] = ()
    has_more: bool = False
    mode: str = "rule"
    status: str = "OK"
