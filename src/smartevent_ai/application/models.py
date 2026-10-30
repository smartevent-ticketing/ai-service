"""Application request/result records, independent of HTTP/Pydantic."""

from dataclasses import dataclass
from uuid import UUID
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re
from typing import Any

from smartevent_ai.domain.dialogue import DialogueState, Grounding, Intent
from smartevent_ai.domain.knowledge import Citation
from smartevent_ai.domain.errors import ContractViolation


@dataclass(frozen=True, slots=True)
class ChatCommand:
    message: str
    conversation_id: UUID | None = None
    previous_state: DialogueState = DialogueState()


@dataclass(frozen=True, slots=True)
class ChatEventLink:
    event_id: str
    title: str
    slug: str


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
        """Validate untrusted projected data before it reaches HTTP serialization."""
        try:
            return cls._from_projection(row)
        except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation) as exc:
            raise ContractViolation("Invalid event card projection") from exc

    @classmethod
    def _from_projection(cls, row: dict[str, Any]) -> "EventCard":
        if not isinstance(row, dict):
            raise ValueError("event must be an object")
        city = row.get("city")
        if city == "" or (isinstance(city, str) and not city.strip()):
            city = None
        venue_name = row.get("venueName")
        if venue_name == "" or (isinstance(venue_name, str) and not venue_name.strip()):
            venue_name = None

        name = row.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError("invalid event text")

        for val, maximum in ((city, 100), (venue_name, 255)):
            if val is not None:
                if not isinstance(val, str) or not val.strip() or len(val) > maximum:
                    raise ValueError("invalid event text")
        for key in ("startTime", "endTime", "priceObservedAt"):
            value = row.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError("event timestamps must be strings")
                instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if instant.tzinfo is None or instant.utcoffset() is None:
                    raise ValueError("event timestamps require a timezone")
        if row.get("startTime") and row.get("endTime"):
            if datetime.fromisoformat(row["startTime"]) >= datetime.fromisoformat(row["endTime"]):
                raise ValueError("event time range must be increasing")
        slug = row["slug"]
        if not isinstance(slug, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,254}", slug):
            raise ValueError("unsafe event slug")
        price = row.get("price")
        if price is not None:
            if isinstance(price, bool) or not isinstance(price, (str, int, float, Decimal)):
                raise ValueError("invalid price type")
            if row.get("currency") != "VND" or not all(
                row.get(k) for k in ("ticketTypeId", "salePhaseId", "priceObservedAt", "priceBasis")
            ):
                raise ValueError("price evidence is incomplete")
            number = Decimal(str(price))
            if not number.is_finite() or number < 0:
                raise ValueError("invalid price")
            price = format(number, "f")
            if row["priceBasis"] != "TICKET_FACE_VALUE":
                raise ValueError("unsupported price basis")
        return cls(
            UUID(row["id"]),
            name,
            slug,
            f"/events/{slug}",
            city,
            venue_name,
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
    event_links: tuple[ChatEventLink, ...] = ()
    has_more: bool = False
    mode: str = "rule"
    status: str = "OK"
