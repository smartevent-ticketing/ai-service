import pytest

from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand
from smartevent_ai.domain.dialogue import DialogueState, Intent
from smartevent_ai.domain.knowledge import PolicyAnswer


@pytest.mark.parametrize(
    "query",
    [
        "Có những cách thanh toán nào",
        "Có hỗ trợ VNPay không?",
        "Co nhung cach thanh toan nao",
        "Thanh toán bằng gì?",
        "Có MoMo không?",
        "Thanh toán thế nào",
        "Có hỗ trợ ZaloPay không",
        "VNPAY là gì",
        "Đặt vé bằng cách nào",
        "Làm sao mua vé",
        "Hướng dẫn tìm sự kiện",
        "Ảnh bìa kích thước bao nhiêu",
        "Tải ảnh định dạng nào",
        "Hướng dẫn xem vé trong tài khoản",
        "Thanh toán tối đa bao nhiêu?",
    ],
)
def test_public_questions_are_not_account_queries(query: str) -> None:
    assert RuleBasedVietnameseNLU().parse(query, DialogueState()).intent is Intent.PUBLIC_HELP


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("Đơn của tôi đã thanh toán chưa", Intent.PAYMENT_STATUS),
        ("Trạng thái thanh toán", Intent.PAYMENT_STATUS),
        ("Tôi đã thanh toán đơn ORD-2026-123", Intent.PAYMENT_STATUS),
        ("Giao dịch của mình thành công chưa", Intent.PAYMENT_STATUS),
        ("Xem đơn hàng của tôi", Intent.ORDER_STATUS),
        ("Xem vé đã mua", Intent.MY_TICKETS),
        ("Giữ vé giúp tôi", Intent.BOOKING_GUIDANCE),
        ("Hủy vé giúp tôi", Intent.BOOKING_GUIDANCE),
        ("Tôi muốn hoàn tiền", Intent.REFUND_POLICY),
    ],
)
def test_private_and_transaction_requests_stay_separate(query: str, intent: Intent) -> None:
    assert RuleBasedVietnameseNLU().parse(query, DialogueState()).intent is intent


@pytest.mark.parametrize(
    ("text", "city"),
    [
        ("Tim su kien o HCM", "Hồ Chí Minh"),
        ("Tìm sự kiện ở Hải Phòng", "Hải Phòng"),
        ("Tim su kien o Can Tho", "Cần Thơ"),
        ("Có sự kiện gì ở Huế", "Huế"),
        ("Tim concert o Da Lat", "Đà Lạt"),
        ("Tìm sự kiện tại Nha Trang", "Nha Trang"),
        ("Tìm sự kiện ở Vũng Tàu", "Vũng Tàu"),
        ("Tim show o Quy Nhon", "Quy Nhơn"),
    ],
)
def test_cities_and_unaccented_search(text: str, city: str) -> None:
    result = RuleBasedVietnameseNLU().parse(text, DialogueState())
    assert result.intent is Intent.SEARCH_EVENT
    assert result.patch.city == city


def test_city_only_followup_preserves_keyword() -> None:
    previous = DialogueState(
        city="Hà Nội", search_query="concert", active_intent=Intent.SEARCH_EVENT
    )
    parsed = RuleBasedVietnameseNLU().parse("Ở Đà Nẵng thì sao?", previous)
    from smartevent_ai.domain.dialogue import merge_state

    next_state = merge_state(previous, parsed.patch)
    assert parsed.intent is Intent.SEARCH_EVENT
    assert next_state.city == "Đà Nẵng" and next_state.search_query == "concert"


@pytest.mark.asyncio
async def test_private_query_never_calls_public_corpus() -> None:
    class NoTools:
        async def execute(self, name, arguments):
            raise AssertionError("No business read authorized")

    class Policies:
        async def answer(self, query):
            raise AssertionError("Private data must never be answered from corpus")

        def status(self):
            return "ready"

    reply = await ChatUseCase(RuleBasedVietnameseNLU(), NoTools(), policies=Policies()).handle(
        ChatCommand(message="Đơn của tôi đã thanh toán chưa")
    )
    assert reply.intent is Intent.PAYMENT_STATUS and not reply.citations


@pytest.mark.asyncio
async def test_general_payment_routes_to_public_corpus_even_without_business_tools() -> None:
    class NoTools:
        async def execute(self, name, arguments):
            raise AssertionError("General payment information is not a business query")

    class Policies:
        def __init__(self):
            self.queries = []

        async def answer(self, query):
            self.queries.append(query)
            return PolicyAnswer("No evidence")

        def status(self):
            return "ready"

    policies = Policies()
    reply = await ChatUseCase(RuleBasedVietnameseNLU(), NoTools(), policies=policies).handle(
        ChatCommand(message="Có những cách thanh toán nào")
    )
    assert reply.intent is Intent.PUBLIC_HELP and len(policies.queries) == 1
    assert "dữ liệu tài khoản" not in reply.answer
