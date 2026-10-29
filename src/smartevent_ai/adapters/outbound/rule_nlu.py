"""Deterministic Vietnamese NLU baseline used before model fine-tuning.

The adapter must never let malformed user text violate domain invariants or
crash the HTTP boundary. It emits typed domain values only.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from typing import Callable
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
    ("tp.hcm", "Hồ Chí Minh"),
    ("hcm", "Hồ Chí Minh"),
    ("ha noi", "Hà Nội"),
    ("ho chi minh", "Hồ Chí Minh"),
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

_CITY_VALUE = "(?:" + "|".join(re.escape(marker) for marker, _ in CITY_ALIASES) + ")"
_CITY_UPDATE = re.compile(
    rf"(?:(?:(?:tìm(?: sự kiện)? )?(?:ở|tại) |"
    rf"(?:đổi|chuyển)(?: thành phố)? (?:sang|thành) )?{_CITY_VALUE}|"
    rf"bỏ(?: bộ lọc)? thành phố(?: {_CITY_VALUE})?|mọi thành phố|"
    rf"tất cả thành phố|không giới hạn thành phố)(?: (?:nhé|ạ|thôi))?[.!?]*"
)


class RuleBasedVietnameseNLU:
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))

    def parse(self, text: str, state: DialogueState) -> Understanding:
        norm = " ".join(text.casefold().strip().split())
        try:
            result = self._parse(text, state)
            patch = result.patch
            start, end = self._dates(norm)
            if start is not None:
                patch = replace(patch, start_from=start, start_before=end)
            if any(x in norm for x in ("bỏ giới hạn ngày", "bỏ ngày", "mọi thời gian")):
                patch = replace(
                    patch, removed_slots=patch.removed_slots | {Slot.START_FROM, Slot.START_BEFORE}
                )
            if result.intent is Intent.POLICY_FAQ:
                patch = replace(
                    patch,
                    faq_topic="thanh toán"
                    if any(x in norm for x in ("thanh toán", "momo", "vnpay", "ví"))
                    else "hướng dẫn",
                )
            merged = merge_state(state, patch)
            reason = result.clarification_reason
            if result.intent is Intent.SEARCH_EVENT and merged.budget_amount is not None:
                if merged.budget_scope is Scope.UNKNOWN:
                    reason = ClarificationReason.BUDGET_SCOPE
                elif merged.budget_scope is Scope.TOTAL and merged.quantity is None:
                    reason = ClarificationReason.QUANTITY_REQUIRED
            return replace(
                result,
                patch=patch,
                needs_clarification=reason is not None,
                clarification_reason=reason,
            )
        except (ValueError, OverflowError):
            return Understanding(
                Intent.CLARIFY,
                needs_clarification=True,
                clarification_reason=ClarificationReason.DATE_INVALID,
            )

    def _dates(self, text: str) -> tuple[datetime | None, datetime | None]:
        local = self._now().astimezone(timezone(timedelta(hours=7)))
        match = re.search(r"tháng\s+(\d{1,2})(?:[ /-](\d{4}))?", text)
        if match:
            month = int(match.group(1))
            year = (
                int(match.group(2))
                if match.group(2)
                else local.year + (int(match.group(1)) < local.month)
            )
        elif "tháng sau" in text:
            month = local.month % 12 + 1
            year = local.year + (local.month == 12)
        else:
            return None, None
        start = datetime(year, month, 1, tzinfo=local.tzinfo)
        end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=local.tzinfo)
        return start, end

    def _parse(self, text: str, state: DialogueState) -> Understanding:
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
        if (
            state.faq_topic
            and norm.startswith(("còn ", "có "))
            and not any(k in norm for k in ("sự kiện", "vé của tôi", "đơn hàng", "giao dịch"))
        ):
            intent = Intent.POLICY_FAQ
        if state.active_intent is Intent.SEARCH_EVENT and (
            "bỏ giới hạn giá" in norm or norm.startswith(("tháng ", "bỏ ngày", "bỏ giới hạn ngày"))
        ):
            intent = Intent.SEARCH_EVENT
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

        if any(x in norm for x in ("bỏ giới hạn ngày", "bỏ ngày", "mọi thời gian")):
            removed.update((Slot.START_FROM, Slot.START_BEFORE))
        if (
            state.active_intent is Intent.SEARCH_EVENT
            and state.budget_scope is Scope.TOTAL
            and state.quantity is None
            and _QUANTITY.fullmatch(norm)
        ):
            intent = Intent.SEARCH_EVENT

        # Only a scope-only reply resumes the active task; a new task wins.
        scope_resolution = self._scope_from_text(norm)
        if (
            state.budget_amount is not None
            and state.budget_scope is Scope.UNKNOWN
            and scope_resolution is not Scope.UNKNOWN
            and _MONEY.search(norm) is None
            and re.fullmatch(
                r"(?:tính |là |cho |ngân sách )*(?:tổng(?: cộng)?|cả nhóm|mỗi vé|"
                r"mỗi ghế|từng vé|một vé|1 vé)(?: (?:nhé|ạ|thôi))?[.!?]*",
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

        city_continuation = (
            clear_group is None
            and state.active_intent in (Intent.SEARCH_EVENT, Intent.TICKET_RECOMMEND)
            and (
                _CITY_UPDATE.fullmatch(norm) is not None
                or bool(removed)
                or norm.startswith("tháng ")
            )
        )
        if city_continuation and state.active_intent is not None:
            # Only a recognized filter-only turn resumes the active task.
            # Explicit account/policy requests and unknown text keep their intent.
            intent = state.active_intent
        search_query = self._extract_search_query(norm) if intent is Intent.SEARCH_EVENT else None
        if intent is Intent.SEARCH_EVENT and search_query is None and not city_continuation:
            removed.add(Slot.SEARCH_QUERY)
        patch = DialoguePatch(
            city=city,
            quantity=quantity,
            budget_amount=budget_amount,
            budget_scope=budget_scope,
            price_comparison=("LT" if "dưới" in norm else "LTE")
            if budget_amount is not None
            else None,
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
        if any(marker in norm for marker in ("mỗi vé", "một vé", "1 vé", "từng vé", "mỗi ghế")):
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
        if any(
            k in norm
            for k in (
                "momo",
                "vnpay",
                "trả tiền kiểu",
                "phương thức thanh toán",
                "hướng dẫn",
                "cách mua",
                "cách thanh toán",
            )
        ) or (
            "thanh toán" in norm
            and any(k in norm for k in ("có ", "không", "bằng "))
            and not any(k in norm for k in ("của tôi", "trạng thái", "đơn hàng"))
        ):
            return Intent.POLICY_FAQ
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
        # Use the slot recognizer at any position; bare title numbers stay intact.
        candidate = " ".join(_QUANTITY.sub(" ", candidate).split())
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
