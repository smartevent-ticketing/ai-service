"""Ollama HTTP adapter for SmartEvent NLU.

Communicates with local Ollama daemon hosting fine-tuned GGUF models.
Enforces strict READ_ONLY boundaries and falls back seamlessly to
deterministic rules on any connection failure, timeout, or malformed JSON.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from smartevent_ai.adapters.outbound.rule_nlu import CITY_ALIASES, RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import (
    MAX_BUDGET_VND,
    ClarificationReason,
    DialoguePatch,
    DialogueState,
    Intent,
    Scope,
    Understanding,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là bộ phân tích NLU SmartEvent v1.2. Nhiệm vụ: Phân tích tin nhắn và xuất DUY NHẤT một khối JSON chứa:\n"
    "- primary_intent: Intent phù hợp (SEARCH_EVENT, TICKET_RECOMMEND, BOOKING_GUIDANCE, REFUND_POLICY, ORDER_STATUS, MY_TICKETS, GREETING, ...)\n"
    "- proposed_action: Hành động chỉ đọc (SEARCH_EVENTS, RUN_TICKET_OPTIMIZER, EXPLAIN_WRITE_LIMITATION, RETRIEVE_POLICY, ...)\n"
    "- entities: dict các thực thể (city, quantity, ticket_type_name, ...)\n"
    "- state_delta: danh sách các thao tác cập nhật trạng thái nếu có.\n"
    "TUYỆT ĐỐI không đề xuất hành động ghi dữ liệu. Xuất JSON hợp lệ."
)


class OllamaNLU:
    """Outbound NLU adapter delegating inference to an external Ollama GGUF server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "smartevent-nlu:1.5b",
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._fallback_nlu = RuleBasedVietnameseNLU()

    def close(self) -> None:
        self._client.close()

    def _normalize_city(self, city: str | None) -> str | None:
        if not city:
            return None
        norm = city.strip().casefold()
        for marker, canonical in CITY_ALIASES:
            if marker in norm or norm in marker:
                return canonical
        return city.strip()

    def _clean_json_str(self, raw: str) -> str:
        s = raw.strip()
        if s.startswith("```"):
            lines = s.split("\n")
            s = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return s.strip()

    def parse(self, text: str, state: DialogueState) -> Understanding:
        try:
            url = f"{self._base_url}/api/chat"
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.0,
                },
            }
            req = self._client.build_request("POST", url, json=payload)
            response = self._client.send(req)
            response.raise_for_status()

            body = response.json()
            raw_content = body.get("message", {}).get("content", "")
            clean_str = self._clean_json_str(raw_content)
            data: dict[str, Any] = json.loads(clean_str)

            # Intent extraction with case-insensitivity
            raw_intent = str(data.get("primary_intent", "")).strip().upper()
            try:
                intent = Intent(raw_intent)
            except ValueError:
                intent = Intent.OUT_OF_SCOPE

            entities: dict[str, Any] = data.get("entities") or {}

            # City normalization
            city = self._normalize_city(entities.get("city"))

            # Search query
            search_query = entities.get("search_query") or entities.get("event_name")
            if intent is Intent.SEARCH_EVENT and not search_query:
                search_query = entities.get("category")

            # Quantity extraction and range check
            quantity = entities.get("quantity")
            if quantity is not None:
                try:
                    qty_int = int(quantity)
                    if not (1 <= qty_int <= 20):
                        return Understanding(
                            intent=intent
                            if intent != Intent.OUT_OF_SCOPE
                            else Intent.TICKET_RECOMMEND,
                            patch=DialoguePatch(
                                city=city,
                                event_name=entities.get("event_name"),
                                search_query=search_query,
                                active_intent=intent,
                            ),
                            needs_clarification=True,
                            clarification_reason=ClarificationReason.QUANTITY_OUT_OF_RANGE,
                        )
                    quantity = qty_int
                except (ValueError, TypeError):
                    quantity = None

            # Budget amount and scope
            budget_amount = entities.get("budget_amount")
            if budget_amount is not None:
                try:
                    b_int = int(budget_amount)
                    if not (0 <= b_int <= MAX_BUDGET_VND):
                        return Understanding(
                            intent=intent,
                            patch=DialoguePatch(
                                city=city,
                                quantity=quantity,
                                event_name=entities.get("event_name"),
                                search_query=search_query,
                                active_intent=intent,
                            ),
                            needs_clarification=True,
                            clarification_reason=ClarificationReason.BUDGET_OUT_OF_RANGE,
                        )
                    budget_amount = b_int
                except (ValueError, TypeError):
                    budget_amount = None

            budget_scope = Scope.UNKNOWN
            raw_scope = entities.get("budget_scope")
            if raw_scope in (Scope.TOTAL, Scope.PER_TICKET):
                budget_scope = Scope(raw_scope)

            # READ_ONLY protection
            proposed_action = data.get("proposed_action", "")
            if proposed_action == "EXPLAIN_WRITE_LIMITATION" or "giữ vé" in text.lower():
                intent = Intent.BOOKING_GUIDANCE

            patch = DialoguePatch(
                city=city,
                quantity=quantity,
                budget_amount=budget_amount,
                budget_scope=budget_scope if budget_amount is not None else None,
                event_name=entities.get("event_name"),
                search_query=search_query,
                active_intent=intent,
            )
            return Understanding(intent=intent, patch=patch)

        except Exception as e:
            logger.warning("OllamaNLU call failed (%s); falling back to RuleBasedNLU", e)
            return self._fallback_nlu.parse(text, state)
