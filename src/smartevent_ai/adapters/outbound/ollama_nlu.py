"""Ollama HTTP adapter for SmartEvent NLU.

Communicates with local Ollama daemon hosting fine-tuned GGUF models.
Enforces strict READ_ONLY boundaries and falls back seamlessly to
deterministic rules on any connection failure, timeout, or malformed JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
import threading
from smartevent_ai.adapters.outbound.model_understanding import parse_model_understanding
import logging
from typing import Any

import httpx

from smartevent_ai.adapters.outbound.rule_nlu import CITY_ALIASES, RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import (
    ClarificationReason,
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
    "Hỗ trợ POLICY_FAQ cho hướng dẫn/thanh toán chung; PAYMENT_STATUS chỉ trạng thái giao dịch cá nhân. entities chỉ dùng city, quantity (số nguyên), budget_amount (số nguyên VND), budget_scope, search_query, event_name, start_from/start_before (ISO-8601 có timezone), price_comparison (LT/LTE), faq_topic. state_delta dùng op SET/REMOVE với slot/value, hoặc op CLEAR với group ALL_SLOTS/EVENT_FILTERS/TICKET_PREFERENCES. TUYỆT ĐỐI không đề xuất hành động ghi dữ liệu. Xuất JSON hợp lệ."
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
        self._inference_slots = threading.BoundedSemaphore(2)

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
        from dataclasses import replace

        if not self._inference_slots.acquire(blocking=False):
            return replace(self._fallback_nlu.parse(text, state), mode="fallback")
        try:
            return self._parse_once(text, state)
        finally:
            self._inference_slots.release()

    def _parse_once(self, text: str, state: DialogueState) -> Understanding:
        try:
            url = f"{self._base_url}/api/chat"
            user_content = text
            if (
                state.active_intent is not None
                or state.city
                or state.quantity
                or state.budget_amount is not None
                or state.event_name
                or state.search_query
            ):
                context_parts = []
                if state.active_intent:
                    context_parts.append(f"active_intent: {state.active_intent.value}")
                if state.city:
                    context_parts.append(f"city: {state.city}")
                if state.quantity:
                    context_parts.append(f"quantity: {state.quantity}")
                if state.budget_amount is not None:
                    context_parts.append(f"budget_amount: {state.budget_amount}")
                if state.budget_scope and state.budget_scope is not Scope.UNKNOWN:
                    context_parts.append(f"budget_scope: {state.budget_scope.value}")
                if state.event_name:
                    context_parts.append(f"event_name: {state.event_name}")
                if state.search_query:
                    context_parts.append(f"search_query: {state.search_query}")
                user_content = (
                    f"Trạng thái trước:\n{{{', '.join(context_parts)}}}\n\n"
                    f"Tin nhắn người dùng: {text}"
                )

            user_content = (
                "Đồng hồ tham chiếu (UTC+07:00): "
                + datetime.now(timezone(timedelta(hours=7))).isoformat()
                + "\n"
                + user_content
            )
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 512,
                },
            }
            req = self._client.build_request("POST", url, json=payload)
            response = self._client.send(req)
            response.raise_for_status()

            body = response.json()
            if (
                not isinstance(body, dict)
                or not isinstance(body.get("message"), dict)
                or not isinstance(body["message"].get("content"), str)
            ):
                raise ValueError("Invalid model response envelope")
            raw_content = body.get("message", {}).get("content", "")
            clean_str = self._clean_json_str(raw_content)
            data: dict[str, Any] = json.loads(clean_str)

            if "giữ vé" in text.lower():
                data["proposed_action"] = "EXPLAIN_WRITE_LIMITATION"
            result = parse_model_understanding(data, state)
            return result

        except (ValueError, TypeError, KeyError):
            return Understanding(
                Intent.CLARIFY,
                needs_clarification=True,
                clarification_reason=ClarificationReason.MODEL_OUTPUT_INVALID,
                mode="fallback",
            )
        except Exception as e:
            logger.warning("OllamaNLU call failed (%s); falling back to RuleBasedNLU", e)
            from dataclasses import replace

            return replace(self._fallback_nlu.parse(text, state), mode="fallback")
