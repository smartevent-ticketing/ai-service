"""Pure dialogue-domain values and invariants.

This module intentionally depends only on the Python standard library. HTTP,
Pydantic, persistence and model-provider concerns belong to outer layers.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from datetime import datetime

MAX_BUDGET_VND = 1_000_000_000
MAX_MESSAGE_STATE_TEXT = 120


class Intent(StrEnum):
    GREETING = "GREETING"
    SEARCH_EVENT = "SEARCH_EVENT"
    EVENT_DETAIL = "EVENT_DETAIL"
    TICKET_RECOMMEND = "TICKET_RECOMMEND"
    TICKET_AVAILABILITY = "TICKET_AVAILABILITY"
    ORDER_STATUS = "ORDER_STATUS"
    PAYMENT_STATUS = "PAYMENT_STATUS"
    MY_TICKETS = "MY_TICKETS"
    POLICY_FAQ = "POLICY_FAQ"
    REFUND_POLICY = "REFUND_POLICY"
    PUBLIC_HELP = "PUBLIC_HELP"
    BOOKING_GUIDANCE = "BOOKING_GUIDANCE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CLARIFY = "CLARIFY"


class Scope(StrEnum):
    TOTAL = "TOTAL"
    PER_TICKET = "PER_TICKET"
    UNKNOWN = "UNKNOWN"


class ClarificationReason(StrEnum):
    DATE_INVALID = "DATE_INVALID"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    QUANTITY_REQUIRED = "QUANTITY_REQUIRED"
    BUDGET_SCOPE = "BUDGET_SCOPE"
    BUDGET_OUT_OF_RANGE = "BUDGET_OUT_OF_RANGE"
    QUANTITY_OUT_OF_RANGE = "QUANTITY_OUT_OF_RANGE"


class Slot(StrEnum):
    CITY = "city"
    QUANTITY = "quantity"
    BUDGET_AMOUNT = "budget_amount"
    BUDGET_SCOPE = "budget_scope"
    EVENT_NAME = "event_name"
    SEARCH_QUERY = "search_query"
    ACTIVE_INTENT = "active_intent"

    START_FROM = "start_from"
    START_BEFORE = "start_before"
    PRICE_COMPARISON = "price_comparison"
    FAQ_TOPIC = "faq_topic"


class ClearGroup(StrEnum):
    ALL_SLOTS = "ALL_SLOTS"
    EVENT_FILTERS = "EVENT_FILTERS"
    TICKET_PREFERENCES = "TICKET_PREFERENCES"


class Grounding(StrEnum):
    NO_LIVE_DATA = "NO_LIVE_DATA"
    BACKEND_READ = "BACKEND_READ"
    APPROVED_CORPUS = "APPROVED_CORPUS"


def _validate_optional_text(name: str, value: str | None, maximum: int) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    if not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1..{maximum} characters")


def _validate_filters(
    start: datetime | None, end: datetime | None, comparison: str | None, topic: str | None
) -> None:
    for value in (start, end):
        if value is not None and (
            not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("event dates must include a timezone")
    if start is not None and end is not None and start >= end:
        raise ValueError("event start range must be increasing")
    if comparison not in (None, "LT", "LTE"):
        raise ValueError("price comparison must be LT or LTE")
    _validate_optional_text("faq_topic", topic, 120)


@dataclass(frozen=True, slots=True)
class DialogueState:
    city: str | None = None
    quantity: int | None = None
    budget_amount: int | None = None
    budget_scope: Scope = Scope.UNKNOWN
    event_name: str | None = None
    search_query: str | None = None
    active_intent: Intent | None = None
    start_from: datetime | None = None
    start_before: datetime | None = None
    price_comparison: str | None = None
    faq_topic: str | None = None

    def __post_init__(self) -> None:
        _validate_filters(self.start_from, self.start_before, self.price_comparison, self.faq_topic)
        if self.budget_amount is None and self.price_comparison is not None:
            raise ValueError("price comparison requires a budget")
        if not isinstance(self.budget_scope, Scope):
            raise ValueError("budget_scope must be a Scope")
        if self.active_intent is not None and not isinstance(self.active_intent, Intent):
            raise ValueError("active_intent must be an Intent")
        _validate_optional_text("city", self.city, 80)
        _validate_optional_text("event_name", self.event_name, MAX_MESSAGE_STATE_TEXT)
        _validate_optional_text("search_query", self.search_query, MAX_MESSAGE_STATE_TEXT)
        if self.quantity is not None and (
            type(self.quantity) is not int or not 1 <= self.quantity <= 20
        ):
            raise ValueError("quantity must be an integer between 1 and 20")
        if self.budget_amount is not None and (
            type(self.budget_amount) is not int or not 0 <= self.budget_amount <= MAX_BUDGET_VND
        ):
            raise ValueError(f"budget_amount must be between 0 and {MAX_BUDGET_VND}")
        if self.budget_amount is None and self.budget_scope is not Scope.UNKNOWN:
            raise ValueError("budget_scope must be UNKNOWN when budget_amount is missing")


@dataclass(frozen=True, slots=True)
class DialoguePatch:
    city: str | None = None
    quantity: int | None = None
    budget_amount: int | None = None
    budget_scope: Scope | None = None
    event_name: str | None = None
    search_query: str | None = None
    active_intent: Intent | None = None
    start_from: datetime | None = None
    start_before: datetime | None = None
    price_comparison: str | None = None
    faq_topic: str | None = None
    removed_slots: frozenset[Slot] = frozenset()
    clear_group: ClearGroup | None = None

    def __post_init__(self) -> None:
        _validate_filters(self.start_from, self.start_before, self.price_comparison, self.faq_topic)
        if self.budget_scope is not None and not isinstance(self.budget_scope, Scope):
            raise ValueError("budget_scope patch must be a Scope")
        if self.active_intent is not None and not isinstance(self.active_intent, Intent):
            raise ValueError("active_intent patch must be an Intent")
        if not isinstance(self.removed_slots, frozenset) or any(
            not isinstance(slot, Slot) for slot in self.removed_slots
        ):
            raise ValueError("removed_slots must contain typed slots")
        if self.clear_group is not None and not isinstance(self.clear_group, ClearGroup):
            raise ValueError("clear_group must be a ClearGroup")
        _validate_optional_text("city", self.city, 80)
        _validate_optional_text("event_name", self.event_name, MAX_MESSAGE_STATE_TEXT)
        _validate_optional_text("search_query", self.search_query, MAX_MESSAGE_STATE_TEXT)
        if self.quantity is not None and (
            type(self.quantity) is not int or not 1 <= self.quantity <= 20
        ):
            raise ValueError("quantity patch is outside the supported range")
        if self.budget_amount is not None and (
            type(self.budget_amount) is not int or not 0 <= self.budget_amount <= MAX_BUDGET_VND
        ):
            raise ValueError("budget patch is outside the supported range")


@dataclass(frozen=True, slots=True)
class Understanding:
    intent: Intent
    patch: DialoguePatch = DialoguePatch()
    needs_clarification: bool = False
    clarification_reason: ClarificationReason | None = None
    mode: str = "rule"

    def __post_init__(self) -> None:
        if not isinstance(self.intent, Intent) or not isinstance(self.patch, DialoguePatch):
            raise ValueError("Understanding requires typed intent and patch")
        if self.clarification_reason is not None and not isinstance(
            self.clarification_reason, ClarificationReason
        ):
            raise ValueError("Invalid clarification reason")
        if self.needs_clarification != (self.clarification_reason is not None):
            raise ValueError("clarification flag and reason must agree")


def merge_state(previous: DialogueState, patch: DialoguePatch) -> DialogueState:
    """Apply CLEAR, REMOVE, then SET; only conversation preferences can change."""
    defaults = DialogueState()
    removed = set(patch.removed_slots)
    if patch.clear_group is ClearGroup.ALL_SLOTS:
        removed.update(Slot)
    elif patch.clear_group is ClearGroup.EVENT_FILTERS:
        removed.update(
            (Slot.CITY, Slot.EVENT_NAME, Slot.SEARCH_QUERY, Slot.START_FROM, Slot.START_BEFORE)
        )
    elif patch.clear_group is ClearGroup.TICKET_PREFERENCES:
        removed.update(
            (Slot.QUANTITY, Slot.BUDGET_AMOUNT, Slot.BUDGET_SCOPE, Slot.PRICE_COMPARISON)
        )
    if Slot.BUDGET_AMOUNT in removed:
        removed.update((Slot.BUDGET_SCOPE, Slot.PRICE_COMPARISON))
    if Slot.START_FROM in removed or Slot.START_BEFORE in removed:
        removed.update((Slot.START_FROM, Slot.START_BEFORE))
    values = {}
    for field in fields(DialogueState):
        value = getattr(defaults if Slot(field.name) in removed else previous, field.name)
        supplied = getattr(patch, field.name)
        values[field.name] = supplied if supplied is not None else value
    return DialogueState(**values)
