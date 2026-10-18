"""Deterministic Vietnamese NLU baseline used before model fine-tuning.

The adapter must never let malformed user text violate domain invariants or
crash the HTTP boundary. It emits typed domain values only.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext

from smartevent_ai.domain.dialogue import (
    MAX_BUDGET_VND,
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

CITY_ALIASES: tuple[tuple[str, str], ...] = (
    ("hà nội", "Hà Nội"),
    ("hồ chí minh", "Hồ Chí Minh"),
    ("tp hcm", "Hồ Chí Minh"),
    ("tp. hcm", "Hồ Chí Minh"),
    ("sài gòn", "Hồ Chí Minh"),
    ("đà nẵng", "Đà Nẵng"),
)

_QUANTITY = re.compile(r"(?<![\w.,])(-?\d+(?:[.,]\d+)?)\s*(?:vé|ghế)(?!\w)")
_MONEY = re.compile(r"(?:dưới|tối đa|không quá)\s*(-?\d+(?:[.,]\d+)?)\s*(triệu|tr|nghìn|ngàn|k)\b")
_SEARCH_CAPTURE = re.compile(
    r"(?:^|\b)tìm(?:\s+cho\s+(?:tôi|mình))?\s+(.+?)(?=\s+(?:ở|tại|dưới|tối đa|không quá)\b|$)"
)


class RuleBasedVietnameseNLU:
    def parse(self, text: str, state: DialogueState) -> Understanding:
        norm = " ".join(text.casefold().strip().split())
        quantity_match = _QUANTITY.search(norm)
        number = Decimal(quantity_match.group(1).replace(",", ".")) if quantity_match else None
        if number is not None and (not 1 <= number <= 20 or number != number.to_integral_value()):
            return Understanding(
                intent=Intent.TICKET_RECOMMEND,
                needs_clarification=True,
                clarification_reason=ClarificationReason.QUANTITY_OUT_OF_RANGE,
            )
        quantity = int(number) if number is not None else None
        city = self._extract_city(norm)
        intent = self._classify_intent(norm)
        removed: set[Slot] = set()
        clear_group = None
        if any(x in norm for x in ("bắt đầu lại", "xóa tất cả tiêu chí", "xóa toàn bộ tiêu chí")):
            clear_group = ClearGroup.ALL_SLOTS
            state = DialogueState()
        if any(
            x in norm
            for x in (
                "bỏ bộ lọc thành phố",
                "bỏ thành phố",
                "mọi thành phố",
                "tất cả thành phố",
                "không giới hạn thành phố",
            )
        ):
            removed.add(Slot.CITY)
        if any(x in norm for x in ("bỏ ngân sách", "không giới hạn ngân sách", "bỏ giới hạn giá")):
            removed.add(Slot.BUDGET_AMOUNT)
            state = merge_state(state, DialoguePatch(removed_slots=frozenset(removed)))

        # Only a scope-only reply resumes the active task; a new task wins.
        scope_resolution = self._scope_from_text(norm)
        if (
            state.budget_amount is not None
            and state.budget_scope is Scope.UNKNOWN
            and scope_resolution is not Scope.UNKNOWN
            and _MONEY.search(norm) is None
            and re.fullmatch(
                r"(?:tính |là |cho |ngân sách )*(?:tổng(?: cộng)?|cả nhóm|mỗi vé|"
                r"mỗi ghế|từng vé|một vé)(?: (?:nhé|ạ|thôi))?[.!?]*",
                norm,
            )
        ):
            return Understanding(
                intent=(
                    state.active_intent
                    if state.active_intent in (Intent.SEARCH_EVENT, Intent.TICKET_RECOMMEND)
                    else Intent.TICKET_RECOMMEND
                ),
                patch=DialoguePatch(
                    city=city,
                    quantity=quantity,
                    budget_scope=scope_resolution,
                ),
            )

        budget_amount: int | None = None
        budget_scope: Scope | None = None
        money = _MONEY.search(norm)
        if money:
            amount = self._money_to_vnd(money.group(1), money.group(2))
            if amount is None or amount > MAX_BUDGET_VND:
                return Understanding(
                    intent=Intent.TICKET_RECOMMEND,
                    patch=DialoguePatch(city=city, quantity=quantity),
                    needs_clarification=True,
                    clarification_reason=ClarificationReason.BUDGET_OUT_OF_RANGE,
                )
            budget_amount = amount
            budget_scope = scope_resolution

        search_query = self._extract_search_query(norm) if intent is Intent.SEARCH_EVENT else None
        if intent is Intent.SEARCH_EVENT and search_query is None:
            removed.add(Slot.SEARCH_QUERY)
        patch = DialoguePatch(
            city=city,
            quantity=quantity,
            budget_amount=budget_amount,
            budget_scope=budget_scope,
            search_query=search_query,
            active_intent=intent if intent is not Intent.CLARIFY else None,
            removed_slots=frozenset(removed),
            clear_group=clear_group,
        )
        next_state = merge_state(state, patch)
        ambiguous_budget = (
            next_state.budget_amount is not None
            and next_state.budget_scope is Scope.UNKNOWN
            and intent in (Intent.SEARCH_EVENT, Intent.TICKET_RECOMMEND)
        )
        return Understanding(
            intent=intent,
            patch=patch,
            needs_clarification=ambiguous_budget,
            clarification_reason=(ClarificationReason.BUDGET_SCOPE if ambiguous_budget else None),
        )

    @staticmethod
    def _extract_city(norm: str) -> str | None:
        matches: list[tuple[int, str]] = []
        for marker, canonical in CITY_ALIASES:
            for match in re.finditer(re.escape(marker), norm):
                prefix = norm[max(0, match.start() - 40) : match.start()]
                if not re.search(
                    r"(?:không (?:ở|chọn)|bỏ(?: bộ lọc)?(?: thành phố)?|ngoại trừ)\s*$", prefix
                ):
                    matches.append((match.start(), canonical))
        return max(matches)[1] if matches else None

    @staticmethod
    def _scope_from_text(norm: str) -> Scope:
        if any(marker in norm for marker in ("mỗi vé", "một vé", "từng vé", "mỗi ghế")):
            return Scope.PER_TICKET
        if any(marker in norm for marker in ("tổng", "tổng cộng", "cả nhóm", "cả 3", "cả 2")):
            return Scope.TOTAL
        return Scope.UNKNOWN

    @staticmethod
    def _money_to_vnd(raw: str, unit: str) -> int | None:
        try:
            number = Decimal(raw.replace(",", "."))
        except InvalidOperation:
            return None
        if not number.is_finite() or number < 0:
            return None
        factor = Decimal(1_000_000 if unit in ("triệu", "tr") else 1_000)
        with localcontext() as context:
            context.prec = max(28, len(raw) + 10)
            amount = number * factor
        if amount != amount.to_integral_value():
            # VND is represented as an integer; reject fractions smaller than one đồng.
            return None
        try:
            return int(amount)
        except (OverflowError, ValueError):
            return None

    @staticmethod
    def _classify_intent(norm: str) -> Intent:
        if any(k in norm for k in ("hoàn tiền", "hoàn vé", "refund")):
            return Intent.REFUND_POLICY
        if "thanh toán" in norm or "giao dịch" in norm:
            return Intent.PAYMENT_STATUS
        if "đơn hàng" in norm or "đơn của" in norm:
            return Intent.ORDER_STATUS
        if "vé của tôi" in norm or "vé đã mua" in norm:
            return Intent.MY_TICKETS
        if any(k in norm for k in ("đặt vé", "giữ vé", "hủy vé", "mua vé")):
            return Intent.BOOKING_GUIDANCE
        if any(k in norm for k in ("tìm", "sự kiện", "concert", "show")):
            return Intent.SEARCH_EVENT
        if "vé" in norm or "ghế" in norm:
            return Intent.TICKET_RECOMMEND
        if any(k in norm for k in ("chào", "hello", "xin chào")):
            return Intent.GREETING
        return Intent.CLARIFY

    @staticmethod
    def _extract_search_query(norm: str) -> str | None:
        match = _SEARCH_CAPTURE.search(norm)
        if not match:
            # A bare domain keyword is still useful for backend full-text search.
            for keyword in ("concert", "show"):
                if keyword in norm:
                    return keyword
            return None

        candidate = match.group(1).strip()
        candidate = re.sub(r"^(?:[1-9]|1\d|20)\s*(?:vé|ghế)\s+", "", candidate)
        candidate = re.sub(r"^sự kiện\s+", "", candidate).strip()
        if candidate in (
            "",
            "sự kiện",
            "vé",
            "ghế",
            "tất cả sự kiện",
            "mọi sự kiện",
        ) or candidate.startswith(("ở ", "tại ")):
            return None
        return candidate[:120]
