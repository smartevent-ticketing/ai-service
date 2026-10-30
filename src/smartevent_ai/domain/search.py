"""Read-only event-search criteria used by application workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from smartevent_ai.domain.dialogue import DialogueState, Scope


@dataclass(frozen=True, slots=True)
class EventSearchCriteria:
    query: str | None = None
    city: str | None = None
    category_id: UUID | None = None
    start_from: datetime | None = None
    start_before: datetime | None = None
    max_price: Decimal | None = None
    price_comparison: str = "LTE"
    page: int = 0
    size: int = 10

    def __post_init__(self) -> None:
        for value in (self.start_from, self.start_before):
            if value is not None and (
                not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError("event dates must include a timezone")
        if self.start_from is not None and self.start_before is not None:
            if self.start_from >= self.start_before:
                raise ValueError("event start range must be increasing")
        if self.price_comparison not in ("LT", "LTE"):
            raise ValueError("invalid price comparison")
        if self.max_price is not None and (
            not isinstance(self.max_price, Decimal)
            or not self.max_price.is_finite()
            or self.max_price < 0
        ):
            raise ValueError("invalid maximum price")
        if self.query is not None and (not self.query.strip() or len(self.query) > 120):
            raise ValueError("search query must contain 1..120 characters")
        if self.city is not None and (not self.city.strip() or len(self.city) > 80):
            raise ValueError("city must contain 1..80 characters")
        if type(self.page) is not int or not 0 <= self.page <= 9:
            raise ValueError("page must be between 0 and 9")
        if type(self.size) is not int or not 1 <= self.size <= 20:
            raise ValueError("size must be between 1 and 20")

    @classmethod
    def from_state(cls, state: DialogueState) -> "EventSearchCriteria":
        price = None
        if state.budget_amount is not None:
            if state.budget_scope is Scope.UNKNOWN:
                raise ValueError("budget scope must be resolved")
            if state.budget_scope is Scope.TOTAL and state.quantity is None:
                raise ValueError("quantity is required for total budget")
            price = Decimal(state.budget_amount) / (
                (state.quantity or 1) if state.budget_scope is Scope.TOTAL else 1
            )
        return cls(
            query=state.search_query,
            city=state.city,
            start_from=state.start_from,
            start_before=state.start_before,
            max_price=price,
            price_comparison=state.price_comparison or "LTE",
        )

    def as_tool_arguments(self) -> dict[str, object]:
        result: dict[str, object] = {"page": self.page, "size": self.size}
        if self.query:
            result["q"] = self.query
        if self.city:
            result["city"] = self.city
        if self.category_id:
            result["categoryId"] = str(self.category_id)
        if self.start_from is not None:
            result["startFrom"] = (
                self.start_from.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        if self.start_before is not None:
            result["startBefore"] = (
                self.start_before.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        if self.max_price is not None:
            result["maxPrice"] = format(self.max_price, "f")
            result["priceComparison"] = self.price_comparison
        return result
