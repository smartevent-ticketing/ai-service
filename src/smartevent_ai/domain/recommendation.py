"""Pure read-only ticket recommendation with explicit completeness invariants."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TicketOption:
    id: str
    price: Decimal
    available: int
    event_published: bool
    phase_active: bool

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Ticket option requires an identifier")
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price < 0:
            raise ValueError("Ticket price must be a finite nonnegative Decimal")
        if type(self.available) is not int or self.available < 0:
            raise ValueError("Availability must be a nonnegative integer")
        if type(self.event_published) is not bool or type(self.phase_active) is not bool:
            raise ValueError("Visibility and sale status must be booleans")


@dataclass(frozen=True, slots=True)
class Recommendation:
    selected: tuple[TicketOption, ...]
    reason: str
    complete_snapshot: bool


def recommend(
    options: tuple[TicketOption, ...],
    *,
    quantity: int,
    max_total: Decimal,
    complete_snapshot: bool,
) -> Recommendation:
    """Rank a complete snapshot; caller must separately prove freshness and quotas."""
    if (
        type(quantity) is not int
        or not 1 <= quantity <= 20
        or not isinstance(max_total, Decimal)
        or not max_total.is_finite()
        or max_total < 0
        or type(complete_snapshot) is not bool
    ):
        raise ValueError("Invalid recommendation criteria")
    if not complete_snapshot:
        return Recommendation((), "INCOMPLETE_SNAPSHOT", False)
    feasible = (
        t
        for t in options
        if t.event_published
        and t.phase_active
        and t.available >= quantity
        and t.price * quantity <= max_total
    )
    ranked = sorted(feasible, key=lambda t: (t.price, t.id))
    return Recommendation(tuple(ranked), "OK" if ranked else "NO_FEASIBLE_OPTION", True)
