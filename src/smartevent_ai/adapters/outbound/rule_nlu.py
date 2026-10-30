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
    ("sai gon", "Hồ Chí Minh"),
    ("đà nẵng", "Đà Nẵng"),
    ("da nang", "Đà Nẵng"),
    ("hải phòng", "Hải Phòng"),
    ("hai phong", "Hải Phòng"),
    ("cần thơ", "Cần Thơ"),
    ("can tho", "Cần Thơ"),
    ("huế", "Huế"),
    ("hue", "Huế"),
    ("đà lạt", "Đà Lạt"),
    ("da lat", "Đà Lạt"),
    ("nha trang", "Nha Trang"),
    ("vũng tàu", "Vũng Tàu"),
    ("vung tau", "Vũng Tàu"),
    ("quy nhơn", "Quy Nhơn"),
    ("quy nhon", "Quy Nhơn"),
)

_QUANTITY = re.compile(r"(?<![\w.,])(-?\d+(?:[.,]\d+)?)\s*(?:vé|ve|ghế|ghe)(?!\w)")
_MONEY = re.compile(
    r"(?:dưới|duoi|tối đa|toi da|không quá|khong qua)\s*(-?\d+(?:[.,]\d+)?)\s*(triệu|trieu|tr|nghìn|nghin|ngàn|ngan|k)\b"
)
_SEARCH_CAPTURE = re.compile(
    r"(?:^|\b)(?:tìm(?:\s+kiếm)?|tim(?:\s+kiem)?)(?:\s+cho\s+(?:tôi|mình|toi|minh))?\s+(.+?)(?=\s+(?:ở|o|tại|tai|dưới|duoi|tối đa|toi da|không quá|khong qua)\b|$)"
)

_CITY_VALUE = "(?:" + "|".join(re.escape(marker) for marker, _ in CITY_ALIASES) + ")"
_CITY_UPDATE = re.compile(
    rf"(?:(?:(?:tìm(?: sự kiện)? )?(?:ở|tại) |"
    rf"(?:đổi|chuyển)(?: thành phố)? (?:sang|thành) )?{_CITY_VALUE}|"
    rf"bỏ(?: bộ lọc)?(?:\s+(?:thành phố|tp\.?|tp))?(?: {_CITY_VALUE})?|"
    rf"không (?:ở|tại|chọn)(?:\s+(?:thành phố|tp\.?|tp))?\s+{_CITY_VALUE}|"
    rf"mọi thành phố|"
    rf"tất cả thành phố|không giới hạn thành phố)(?: (?:thì sao|thi sao|nhé|nhe|ạ|a|thôi|thoi))?[.!?]*"
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
            if any(
                x in norm for x in ("bỏ giới hạn ngày", "bỏ ngày", "mọi thời gian")
            ) or re.search(r"\b(?:bỏ|bo)\s+tháng(?:\s+\d{1,2})?\b", norm):
                patch = replace(
                    patch, removed_slots=patch.removed_slots | {Slot.START_FROM, Slot.START_BEFORE}
                )
            if result.intent in (Intent.POLICY_FAQ, Intent.PUBLIC_HELP, Intent.REFUND_POLICY):
                patch = replace(
                    patch,
                    faq_topic="thanh toán"
                    if any(x in norm for x in ("thanh toán", "momo", "vnpay", "ví"))
                    else "hoàn tiền"
                    if any(x in norm for x in ("hoàn", "refund"))
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
        match = None
        for m in re.finditer(r"tháng\s+(\d{1,2})(?:[ /-](\d{4}))?", text):
            prefix = text[: m.start()]
            if re.search(r"(?:bỏ|bo)\s*$", prefix):
                continue
            match = m
            break
        if match:
            month = int(match.group(1))
            year = (
                int(match.group(2))
                if match.group(2)
                else local.year + (int(match.group(1)) < local.month)
            )
        elif "tháng sau" in text and not re.search(r"(?:bỏ|bo)\s+tháng sau", text):
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
            and state.active_intent in (Intent.POLICY_FAQ, Intent.PUBLIC_HELP, Intent.REFUND_POLICY)
            and intent
            in (Intent.CLARIFY, Intent.PUBLIC_HELP, Intent.POLICY_FAQ, Intent.REFUND_POLICY)
            and norm.startswith(("còn ", "con "))
            and not any(k in norm for k in ("sự kiện", "vé của tôi", "đơn hàng", "giao dịch"))
        ):
            intent = (
                state.active_intent
                if state.active_intent is Intent.REFUND_POLICY
                else Intent.POLICY_FAQ
            )
        if state.active_intent is Intent.SEARCH_EVENT and (
            "bỏ giới hạn giá" in norm
            or norm.startswith(("tháng ", "bỏ ngày", "bỏ giới hạn ngày", "bỏ tháng"))
            or re.search(r"\b(?:bỏ|bo)\s+tháng(?:\s+\d{1,2})?\b", norm)
        ):
            intent = Intent.SEARCH_EVENT
        removed: set[Slot] = set()
        clear_group = None
        if any(x in norm for x in ("bắt đầu lại", "xóa tất cả tiêu chí", "xóa toàn bộ tiêu chí")):
            clear_group = ClearGroup.ALL_SLOTS
            state = DialogueState()
        if (
            any(
                x in norm
                for x in (
                    "bỏ bộ lọc thành phố",
                    "bỏ thành phố",
                    "mọi thành phố",
                    "tất cả thành phố",
                    "không giới hạn thành phố",
                )
            )
            or re.search(
                rf"\b(?:bỏ|bo)(?:\s+bộ lọc)?(?:\s+(?:thành phố|tp\.?|tp))?\s+{_CITY_VALUE}\b",
                norm,
            )
            or (
                city is None
                and re.search(
                    rf"\b(?:không (?:ở|tại|chọn)|ngoại trừ)(?:\s+(?:thành phố|tp\.?|tp))?\s+{_CITY_VALUE}\b",
                    norm,
                )
            )
        ):
            removed.add(Slot.CITY)
        if any(x in norm for x in ("bỏ ngân sách", "không giới hạn ngân sách", "bỏ giới hạn giá")):
            removed.add(Slot.BUDGET_AMOUNT)
            state = merge_state(state, DialoguePatch(removed_slots=frozenset(removed)))

        if any(x in norm for x in ("bỏ giới hạn ngày", "bỏ ngày", "mọi thời gian")) or re.search(
            r"\b(?:bỏ|bo)\s+tháng(?:\s+\d{1,2})?\b", norm
        ):
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
                r"(?:tính |tinh |là |la |cho |ngân sách |ngan sach )*(?:tổng(?: cộng)?|tong(?: cong)?|cả nhóm|ca nhom|mỗi vé|moi ve|"
                r"mỗi ghế|moi ghe|từng vé|tung ve|một vé|mot ve|1\s*vé|1\s*ve|1ve|1ghe)(?: (?:nhé|nhe|ạ|a|thôi|thoi))?[.!?]*",
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
                or budget_amount is not None
            )
        )
        if city_continuation and state.active_intent is not None:
            # Only a recognized filter-only turn resumes the active task.
            # Explicit account/policy requests and unknown text keep their intent.
            intent = state.active_intent
        search_query = self._extract_search_query(norm) if intent is Intent.SEARCH_EVENT else None
        if (
            intent is Intent.SEARCH_EVENT
            and search_query is None
            and not city_continuation
            and not (state.search_query and budget_amount is not None)
        ):
            removed.add(Slot.SEARCH_QUERY)
        patch = DialoguePatch(
            city=city,
            quantity=quantity,
            budget_amount=budget_amount,
            budget_scope=budget_scope,
            price_comparison=("LT" if any(word in norm for word in ("dưới", "duoi")) else "LTE")
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
            for match in re.finditer(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", norm):
                prefix = norm[max(0, match.start() - 40) : match.start()]
                if not re.search(
                    r"(?:không (?:ở|tại|chọn|phải(?: ở)?)|bỏ(?: bộ lọc)?|ngoại trừ)\s*(?:(?:thành phố|tp\.?|tp)\s*)?$",
                    prefix,
                ):
                    matches.append((match.start(), canonical))
        return max(matches)[1] if matches else None

    @staticmethod
    def _scope_from_text(norm: str) -> Scope:
        lowered = norm.lower()
        if any(
            marker in lowered
            for marker in (
                "mỗi vé",
                "moi ve",
                "một vé",
                "mot ve",
                "1 vé",
                "1ve",
                "từng vé",
                "tung ve",
                "mỗi ghế",
                "moi ghe",
            )
        ):
            return Scope.PER_TICKET
        if any(
            marker in lowered
            for marker in (
                "tổng",
                "tong",
                "tổng cộng",
                "tong cong",
                "cả nhóm",
                "ca nhom",
                "cả 3",
                "ca 3",
                "cả 2",
                "ca 2",
            )
        ):
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
        unit_fold = unit.lower()
        factor = Decimal(1_000_000 if unit_fold in ("triệu", "trieu", "tr") else 1_000)
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
        if any(k in norm for k in ("hoàn tiền", "hoan tien", "hoàn vé", "hoan ve", "refund")):
            return Intent.REFUND_POLICY
        payment = any(k in norm for k in ("thanh toán", "thanh toan", "giao dịch", "giao dich"))
        private = any(
            k in norm
            for k in (
                "của tôi",
                "cua toi",
                "của mình",
                "cua minh",
                "đơn tôi",
                "don toi",
                "đơn mình",
                "don minh",
                "tôi đã thanh toán",
                "toi da thanh toan",
                "trạng thái",
                "trang thai",
                "thành công chưa",
                "thanh cong chua",
                "đã thanh toán chưa",
                "da thanh toan chua",
                "kiểm tra đơn",
                "kiem tra don",
            )
        ) or bool(re.search(r"\bord[- ]\w+", norm))
        if payment and private:
            return Intent.PAYMENT_STATUS
        if any(k in norm for k in ("đơn hàng", "don hang", "đơn của", "don cua")) and private:
            return Intent.ORDER_STATUS
        if any(k in norm for k in ("vé của tôi", "ve cua toi", "vé của mình", "ve cua minh")):
            return Intent.MY_TICKETS
        if any(
            k in norm
            for k in (
                "giữ vé",
                "giu ve",
                "hủy vé",
                "huy ve",
                "chuyển vé",
                "chuyen ve",
                "đặt hộ",
                "dat ho",
                "mua hộ",
                "mua ho",
            )
        ):
            return Intent.BOOKING_GUIDANCE
        help_request = any(
            k in norm
            for k in (
                "cách",
                "cach",
                "hướng dẫn",
                "huong dan",
                "thế nào",
                "the nao",
                "làm sao",
                "lam sao",
                "vì sao",
                "vi sao",
                "tại sao",
                "tai sao",
                "ở đâu",
                "o dau",
                "hỗ trợ",
                "ho tro",
                "phương thức",
                "phuong thuc",
                "định dạng",
                "dinh dang",
                "dung lượng",
                "dung luong",
                "kích thước",
                "kich thuoc",
                "là gì",
                "la gi",
                "đăng nhập",
                "dang nhap",
                "mật khẩu",
                "mat khau",
                "tối đa bao nhiêu",
                "toi da bao nhieu",
                "bằng gì",
                "bang gi",
            )
        )
        product_topic = any(
            k in norm
            for k in (
                "vé",
                "ve",
                "sự kiện",
                "su kien",
                "thanh toán",
                "thanh toan",
                "đơn hàng",
                "don hang",
                "ảnh",
                "anh",
                "banner",
                "tài khoản",
                "tai khoan",
                "đăng nhập",
                "dang nhap",
                "mật khẩu",
                "mat khau",
                "momo",
                "zalopay",
                "paypal",
                "vnpay",
                "chuyển khoản",
                "chuyen khoan",
            )
        )
        if "thanh toán momo" in norm or "thanh toan momo" in norm:
            return Intent.POLICY_FAQ
        if (
            payment
            or (help_request and product_topic)
            or any(k in norm for k in ("momo", "zalopay", "paypal", "vnpay"))
        ):
            return Intent.PUBLIC_HELP
        if "vé đã mua" in norm or "ve da mua" in norm:
            return Intent.MY_TICKETS
        if any(k in norm for k in ("đặt vé", "dat ve", "mua vé", "mua ve")):
            return Intent.BOOKING_GUIDANCE
        if any(k in norm for k in ("tìm", "tim", "sự kiện", "su kien", "concert", "show")):
            return Intent.SEARCH_EVENT
        if "vé" in norm or "ve" in norm or "ghế" in norm or "ghe" in norm:
            return Intent.TICKET_RECOMMEND
        if any(k in norm for k in ("chào", "chao", "hello", "xin chào", "xin chao")):
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
        candidate = re.sub(r"^(?:sự kiện|su kien)\s+", "", candidate).strip()
        candidate = re.sub(r"^(?:vé sự kiện|ve su kien)\s+", "", candidate).strip()
        candidate = re.sub(r"^(?:kiếm vé sự kiện|kiem ve su kien)\s+", "", candidate).strip()
        if candidate in (
            "",
            "sự kiện",
            "su kien",
            "vé",
            "ve",
            "ghế",
            "ghe",
            "vé sự kiện",
            "ve su kien",
            "kiếm vé sự kiện",
            "kiem ve su kien",
            "tất cả sự kiện",
            "tat ca su kien",
            "mọi sự kiện",
            "moi su kien",
        ) or candidate.startswith(("ở ", "tại ", "o ", "tai ")):
            return None
        return candidate[:120]
