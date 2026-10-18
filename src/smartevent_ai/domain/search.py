"""Read-only event-search criteria used by application workflows."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from smartevent_ai.domain.dialogue import DialogueState


@dataclass(frozen=True, slots=True)
class EventSearchCriteria:
    query: str | None = None
    city: str | None = None
    category_id: UUID | None = None
    page: int = 0
    size: int = 10

    def __post_init__(self) -> None:
        if self.query is not None and (not self.query.strip() or len(self.query) > 120):
            raise ValueError("search query must contain 1..120 characters")
        if self.city is not None and (not self.city.strip() or len(self.city) > 80):
            raise ValueError("city must contain 1..80 characters")
        if not 0 <= self.page <= 9:
            raise ValueError("page must be between 0 and 9")
        if not 1 <= self.size <= 20:
            raise ValueError("size must be between 1 and 20")

    @classmethod
    def from_state(cls, state: DialogueState) -> "EventSearchCriteria":
        return cls(query=state.search_query, city=state.city)

    def as_tool_arguments(self) -> dict[str, object]:
        result: dict[str, object] = {"page": self.page, "size": self.size}
        if self.query:
            result["q"] = self.query
        if self.city:
            result["city"] = self.city
        if self.category_id:
            result["categoryId"] = str(self.category_id)
        return result
