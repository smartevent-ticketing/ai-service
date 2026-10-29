"""One strict model-output boundary shared by Ollama and PEFT."""

from datetime import datetime
from typing import Any
from smartevent_ai.domain.dialogue import (
    ClearGroup,
    ClarificationReason,
    DialoguePatch,
    DialogueState,
    Intent,
    Scope,
    Slot,
    Understanding,
    merge_state,
)


def parse_model_understanding(payload: dict[str, Any], state: DialogueState) -> Understanding:
    if not isinstance(payload, dict) or set(payload) - {
        "primary_intent",
        "entities",
        "state_delta",
        "proposed_action",
    }:
        raise ValueError("unknown model output fields")
    intent = Intent(str(payload.get("primary_intent", "")).strip().upper())
    entities = payload.get("entities") or {}
    if not isinstance(entities, dict):
        raise ValueError("entities must be an object")
    allowed = {s.value for s in Slot} | {"category", "ticket_type_name"}
    if set(entities) - allowed:
        raise ValueError("unknown entity")
    values = {
        key: value
        for key, value in entities.items()
        if key in {s.value for s in Slot} and value is not None
    }
    if "active_intent" in values:
        raise ValueError("entities cannot override routing")
    if "search_query" not in values and intent is Intent.SEARCH_EVENT:
        query = entities.get("event_name") or entities.get("category")
        if query:
            values["search_query"] = query
    removed: set[Slot] = set()
    clear = None
    delta = payload.get("state_delta") or []
    if not isinstance(delta, list) or len(delta) > 20:
        raise ValueError("invalid state_delta")
    for operation in delta:
        if not isinstance(operation, dict) or set(operation) - {
            "op",
            "operation",
            "slot",
            "value",
            "group",
        }:
            raise ValueError("invalid state operation")
        op = str(operation.get("op", operation.get("operation", "SET"))).upper()
        if op == "CLEAR":
            clear = ClearGroup(operation.get("group", "ALL_SLOTS"))
        else:
            raw_slot = operation.get("slot")
            if not isinstance(raw_slot, str):
                raise ValueError("slot must be a string")
            slot = Slot(raw_slot)
            if slot is Slot.ACTIVE_INTENT:
                raise ValueError("state_delta cannot override routing")
            if op == "REMOVE":
                removed.add(slot)
                values.pop(slot.value, None)
            elif op == "SET" and operation.get("value") is not None:
                values[slot.value] = operation["value"]
            else:
                raise ValueError("invalid state operation")
    for key in ("quantity", "budget_amount"):
        value = values.get(key)
        if value is not None and type(value) is not int:
            raise ValueError("numeric entities must be strict integers")
    quantity = values.get("quantity")
    if quantity is not None and not 1 <= quantity <= 20:
        return Understanding(
            intent,
            needs_clarification=True,
            clarification_reason=ClarificationReason.QUANTITY_OUT_OF_RANGE,
            mode="model",
        )
    amount = values.get("budget_amount")
    if amount is not None and not 0 <= amount <= 1_000_000_000:
        return Understanding(
            intent,
            needs_clarification=True,
            clarification_reason=ClarificationReason.BUDGET_OUT_OF_RANGE,
            mode="model",
        )
    for key in ("start_from", "start_before"):
        if key in values:
            if not isinstance(values[key], str):
                raise ValueError("dates must be ISO strings")
            values[key] = datetime.fromisoformat(values[key].replace("Z", "+00:00"))
    if "budget_scope" in values:
        values["budget_scope"] = Scope(str(values["budget_scope"]).strip().upper())
    if "city" in values:
        from smartevent_ai.adapters.outbound.rule_nlu import CITY_ALIASES

        if not isinstance(values["city"], str):
            raise ValueError("city must be text")
        values["city"] = next(
            (canonical for alias, canonical in CITY_ALIASES if alias in values["city"].casefold()),
            values["city"],
        )
    if amount is not None and "budget_scope" not in values:
        values["budget_scope"] = Scope.UNKNOWN
    if amount is not None and values.get("budget_scope") is Scope.UNKNOWN:
        removed.add(Slot.BUDGET_SCOPE)
    if payload.get("proposed_action") == "EXPLAIN_WRITE_LIMITATION":
        intent = Intent.BOOKING_GUIDANCE
    patch = DialoguePatch(
        **values, active_intent=intent, removed_slots=frozenset(removed), clear_group=clear
    )
    merged = merge_state(state, patch)
    reason = None
    if (
        intent in (Intent.SEARCH_EVENT, Intent.TICKET_RECOMMEND)
        and merged.budget_amount is not None
    ):
        if merged.budget_scope is Scope.UNKNOWN:
            reason = ClarificationReason.BUDGET_SCOPE
        elif merged.budget_scope is Scope.TOTAL and merged.quantity is None:
            reason = ClarificationReason.QUANTITY_REQUIRED
    return Understanding(intent, patch, reason is not None, reason, mode="model")
