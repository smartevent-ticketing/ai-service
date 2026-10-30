"""Explicit v1.2 checkpoint compatibility; all output still passes runtime validation."""

import json
import re
import unicodedata
from datetime import datetime
from typing import Any

from smartevent_ai.adapters.outbound.rule_nlu import CITY_ALIASES, RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import DialogueState

TRAINING_PROMPT = (
    "Bạn là bộ phân tích NLU cho hệ thống đặt vé SmartEvent v1.2.\n"
    "Nhiệm vụ: Phân tích yêu cầu người dùng và trích xuất JSON duy nhất gồm:\n"
    "- primary_intent: Một trong 21 intent theo ontology (SEARCH_EVENT, TICKET_RECOMMEND, BOOKING_GUIDANCE, REFUND_POLICY, ...)\n"
    "- proposed_action: Hành động đề xuất chỉ đọc (SEARCH_EVENTS, GET_TICKET_OPTIONS, ...)\n"
    "- entities: dict chứa các thực thể đã bóc tách (city, quantity, budget_amount, budget_currency, ...)\n"
    '- state_delta: list các thao tác cập nhật trạng thái hội thoại [{"operation": "SET", "slot": "...", "value": ...}]\n'
    "Chỉ xuất duy nhất khối JSON, không giải thích thêm."
)


def folded(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))


def merge_entities(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            if (
                key != "entities"
                or not isinstance(value, dict)
                or not isinstance(result[key], dict)
            ):
                raise ValueError("Ambiguous duplicate checkpoint fields")
            if any(k in result[key] and result[key][k] != v for k, v in value.items()):
                raise ValueError("Conflicting checkpoint entities")
            result[key].update(value)
        else:
            result[key] = value
    return result


def adapt_checkpoint(
    raw: str, text: str, state: DialogueState, rules: RuleBasedVietnameseNLU
) -> dict[str, Any]:
    payload = json.loads(raw, object_pairs_hook=merge_entities)
    if not isinstance(payload, dict):
        raise ValueError("Invalid checkpoint payload")
    entities = payload.get("entities", {})
    delta = payload.get("state_delta", [])
    if not isinstance(entities, dict) or not isinstance(delta, list):
        raise ValueError("Invalid checkpoint entities or operations")
    canonical = rules.parse(text, state).patch
    dates: dict[str, str] = {}
    if canonical.start_from is not None and canonical.start_before is not None:
        dates.update(
            start_from=canonical.start_from.isoformat(),
            start_before=canonical.start_before.isoformat(),
        )

    def matches_city(value: Any) -> bool:
        if not isinstance(value, str):
            raise ValueError("City must be text")
        key = folded(value.strip())
        normalized = next(
            (folded(city) for alias, city in CITY_ALIASES if folded(alias) == key), key
        )
        return normalized == folded(canonical.city or "")

    def legacy_value(slot: str, value: Any) -> bool:
        if slot == "budget_currency":
            if value != "VND":
                raise ValueError("Only VND currency is supported")
            return True
        if slot == "month":
            if (
                not isinstance(value, (str, int))
                or isinstance(value, bool)
                or canonical.start_from is None
                or canonical.start_before is None
            ):
                raise ValueError("Month needs explicit user evidence")
            month = str(value)
            if month.isdigit():
                month = "tháng " + month
            supplied = rules.parse("Tìm sự kiện " + month, DialogueState()).patch
            if (
                supplied.start_from != canonical.start_from
                or supplied.start_before != canonical.start_before
            ):
                raise ValueError("Checkpoint month conflicts with the user request")
            dates.update(
                start_from=canonical.start_from.isoformat(),
                start_before=canonical.start_before.isoformat(),
            )
            return True
        if slot == "category":
            if not isinstance(value, str):
                raise ValueError("Category must be text")
            if not re.search(r"(?<!\w)" + re.escape(folded(value)) + r"(?!\w)", folded(text)):
                return True  # Unrequested category guesses must not become filters.
        return False

    for slot in tuple(entities):
        if slot in ("event_name", "search_query", "city", "faq_topic") and entities[slot] == "":
            del entities[slot]
            continue
        if legacy_value(slot, entities[slot]):
            del entities[slot]
    operations = []
    for operation in delta:
        if not isinstance(operation, dict):
            raise ValueError("Invalid checkpoint operation")
        slot = operation.get("slot")
        op = operation.get("op", operation.get("operation", "SET"))
        if (
            op == "SET"
            and slot in dates
            and datetime.fromisoformat(str(operation.get("value")).replace("Z", "+00:00"))
            != datetime.fromisoformat(dates[slot])
        ):
            raise ValueError("Checkpoint date conflicts with the user request")
        if (
            op == "SET"
            and slot == "budget_amount"
            and canonical.budget_amount is not None
            and operation.get("value") != canonical.budget_amount
        ):
            raise ValueError("Checkpoint budget conflicts with the user request")
        if (
            op == "SET"
            and slot in ("event_name", "search_query", "city", "faq_topic")
            and operation.get("value") == ""
        ):
            continue  # Empty legacy placeholders are not REMOVE operations.
        if (
            slot == "city"
            and op == "SET"
            and canonical.city
            and not matches_city(operation.get("value"))
        ):
            raise ValueError("Checkpoint city operation conflicts with explicit user city")
        if (
            slot == "price_comparison"
            and op == "SET"
            and canonical.price_comparison
            and operation.get("value") != canonical.price_comparison
        ):
            raise ValueError("Checkpoint price operator conflicts with the user request")
        if slot in ("month", "budget_currency", "category"):
            if op != "SET":
                raise ValueError("Unsupported legacy operation")
            if legacy_value(slot, operation.get("value")):
                continue
            if slot == "category":
                operations.append(
                    {"op": "SET", "slot": "search_query", "value": operation["value"]}
                )
                continue
        if slot == "budget_scope" and operation.get("value") == "AMOUNT":
            operation = {**operation, "value": "UNKNOWN"}
        operations.append(operation)
    if entities.get("budget_scope") == "AMOUNT":
        entities["budget_scope"] = "UNKNOWN"
    if payload.get("primary_intent") == "TOOLBAR_PAYMENT_METHOD":
        payload["primary_intent"] = "PUBLIC_HELP"
    if canonical.city and entities.get("city") and not matches_city(entities["city"]):
        raise ValueError("Checkpoint city conflicts with explicit user city")
    if (
        canonical.budget_amount is not None
        and entities.get("budget_amount", canonical.budget_amount) != canonical.budget_amount
    ):
        raise ValueError("Checkpoint budget conflicts with the user request")
    if canonical.search_query and "search_query" not in entities:
        entities["search_query"] = canonical.search_query
    if canonical.price_comparison:
        if (
            entities.get("price_comparison", canonical.price_comparison)
            != canonical.price_comparison
        ):
            raise ValueError("Checkpoint price operator conflicts with the user request")
        entities["price_comparison"] = canonical.price_comparison
    if canonical.budget_scope is not None and canonical.budget_scope.value == "UNKNOWN":
        entities["budget_scope"] = "UNKNOWN"
        operations = [
            {**op, "value": "UNKNOWN"}
            if op.get("slot") == "budget_scope"
            and op.get("op", op.get("operation", "SET")) == "SET"
            else op
            for op in operations
        ]
    if any(
        key in entities
        and datetime.fromisoformat(str(entities[key]).replace("Z", "+00:00"))
        != datetime.fromisoformat(value)
        for key, value in dates.items()
    ):
        raise ValueError("Checkpoint date conflicts with the user request")
    entities.update(dates)
    payload["entities"], payload["state_delta"] = entities, operations
    return payload
