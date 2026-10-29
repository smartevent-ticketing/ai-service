"""Cross-boundary regressions for the R2 contract; no live approvals are implied."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import asyncio
import pytest
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.adapters.outbound.model_understanding import parse_model_understanding
from smartevent_ai.adapters.inbound.http_api import DialogueStateDTO, ChatResponseDTO
from smartevent_ai.domain.dialogue import DialogueState, Intent, Scope, merge_state
from smartevent_ai.domain.search import EventSearchCriteria
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand, EventCard

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def test_acceptance_sequence_keeps_price_dates_city_and_resumes_search():
    nlu = RuleBasedVietnameseNLU(lambda: NOW)
    first = nlu.parse("Tìm sự kiện ở TP.HCM dưới 500k trong tháng 11", DialogueState())
    state = merge_state(DialogueState(), first.patch)
    assert state.city == "Hồ Chí Minh"
    assert first.needs_clarification
    second = nlu.parse("1 vé", state)
    state = merge_state(state, second.patch)
    assert second.intent is Intent.SEARCH_EVENT and not second.needs_clarification
    args = EventSearchCriteria.from_state(state).as_tool_arguments()
    assert args["maxPrice"] == "500000" and args["priceComparison"] == "LT"
    assert args["startFrom"] == "2026-11-01T00:00:00+07:00"
    assert args["startBefore"] == "2026-12-01T00:00:00+07:00"
    third = nlu.parse("Đổi sang Hà Nội", state)
    state = merge_state(state, third.patch)
    assert state.city == "Hà Nội" and state.budget_amount == 500000
    fourth = nlu.parse("bỏ giới hạn giá", state)
    state = merge_state(state, fourth.patch)
    assert fourth.intent is Intent.SEARCH_EVENT and state.budget_scope is Scope.UNKNOWN
    assert state.price_comparison is None and state.start_from is not None
    assert "maxPrice" not in EventSearchCriteria.from_state(state).as_tool_arguments()


@pytest.mark.parametrize("text", ["tháng 13", "tháng 0", "tháng 99"])
def test_invalid_month_never_reaches_tool(text):
    understood = RuleBasedVietnameseNLU(lambda: NOW).parse("Tìm sự kiện " + text, DialogueState())
    assert understood.needs_clarification


def test_relative_month_rollover_and_clear_dates():
    nlu = RuleBasedVietnameseNLU(lambda: datetime(2026, 12, 31, tzinfo=timezone.utc))
    result = nlu.parse("Tìm sự kiện tháng sau", DialogueState())
    state = merge_state(DialogueState(), result.patch)
    assert state.start_from.year == 2027 and state.start_from.month == 1
    result = nlu.parse("bỏ giới hạn ngày", state)
    state = merge_state(state, result.patch)
    assert state.start_from is None and state.start_before is None


@pytest.mark.parametrize("value", [2.9, 2.0, True, "2"])
def test_model_quantity_is_strict(value):
    with pytest.raises(ValueError):
        parse_model_understanding(
            {"primary_intent": "SEARCH_EVENT", "entities": {"quantity": value}}, DialogueState()
        )


@pytest.mark.parametrize("operation", ["REMOVE", "CLEAR"])
def test_model_delta_clears_budget_and_operator(operation):
    state = DialogueState(
        city="Hà Nội", budget_amount=500000, budget_scope=Scope.PER_TICKET, price_comparison="LT"
    )
    delta = (
        {"op": "REMOVE", "slot": "budget_amount"}
        if operation == "REMOVE"
        else {"op": "CLEAR", "group": "ALL_SLOTS"}
    )
    result = parse_model_understanding(
        {"primary_intent": "SEARCH_EVENT", "state_delta": [delta]}, state
    )
    merged = merge_state(state, result.patch)
    assert merged.budget_amount is None and merged.budget_scope is Scope.UNKNOWN
    assert merged.price_comparison is None


def test_old_dto_and_new_dto_roundtrip_and_forbid_unknown():
    old = DialogueStateDTO.model_validate({"city": "Hà Nội"})
    assert old.to_domain().start_from is None
    state = DialogueState(start_from=NOW, start_before=datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert DialogueStateDTO.from_domain(state).to_domain() == state
    with pytest.raises(ValueError):
        DialogueStateDTO.model_validate({"unexpected": 1})
    with pytest.raises(ValueError):
        DialogueStateDTO.model_validate({"start_from": "2026-11-01T00:00:00"})


def test_total_budget_uses_quantity_and_preserves_strict_comparison():
    state = DialogueState(
        quantity=2, budget_amount=500000, budget_scope=Scope.TOTAL, price_comparison="LT"
    )
    args = EventSearchCriteria.from_state(state).as_tool_arguments()
    assert Decimal(args["maxPrice"]) == Decimal(250000) and args["priceComparison"] == "LT"
    with pytest.raises(ValueError):
        EventSearchCriteria.from_state(replace(state, quantity=None))


def test_card_rejects_unsafe_slug_and_incomplete_price():
    row = {"id": str(uuid4()), "slug": "concert", "name": "Concert"}
    assert EventCard.from_projection(row).detail_path == "/events/concert"
    with pytest.raises(ValueError):
        EventCard.from_projection({**row, "slug": "../admin"})
    with pytest.raises(ValueError):
        EventCard.from_projection({**row, "price": 100000})


def _inline_run(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("This orchestration probe must not perform external IO")


def test_application_preserves_cards_and_criteria_without_network(monkeypatch):
    # Replace scheduling only; exercise the production coroutine and domain mappings.
    async def inline(function, *args):
        return function(*args)

    monkeypatch.setattr(asyncio, "to_thread", inline)

    async def inline_wait(coroutine, timeout):
        return await coroutine

    monkeypatch.setattr(asyncio, "wait_for", inline_wait)

    class Tools:
        async def execute(self, name, args):
            assert args["maxPrice"] == "500000" and "startFrom" in args
            return {"data": [{"id": str(uuid4()), "name": "Concert", "slug": "concert"}]}

    result = _inline_run(
        ChatUseCase(RuleBasedVietnameseNLU(lambda: NOW), Tools()).handle(
            ChatCommand("Tìm sự kiện ở Hà Nội dưới 500k mỗi vé trong tháng 11")
        )
    )
    response = ChatResponseDTO.from_result(result)
    assert (
        response.events[0].name == "Concert" and response.events[0].detail_path == "/events/concert"
    )


def test_faq_payment_routing_and_account_boundary():
    nlu = RuleBasedVietnameseNLU()
    faq = nlu.parse("Có thanh toán MoMo không?", DialogueState())
    assert faq.intent is Intent.POLICY_FAQ
    state = merge_state(DialogueState(), faq.patch)
    assert nlu.parse("Còn VNPay?", state).intent is Intent.POLICY_FAQ
    assert (
        nlu.parse("Trạng thái thanh toán đơn hàng của tôi", state).intent is Intent.PAYMENT_STATUS
    )


def test_remote_reader_cannot_bypass_rag_gates(tmp_path):
    import yaml
    from smartevent_ai.infrastructure.knowledge_runtime import GateControlledPolicyReader

    class Reader:
        answer_mode = "remote_extractive"

        def status(self):
            return "last_read_ok"

        async def answer(self, query):
            raise AssertionError("disabled gates must not call the service")

    path = tmp_path / "gates.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "gates": {
                    "RAG-APPROVED-CORPUS": {"status": "PASS"},
                    "RAG-READONLY": {"status": "BLOCKED"},
                }
            }
        ),
        encoding="utf-8",
    )
    reader = GateControlledPolicyReader(Reader(), path)
    assert reader.status() == "disabled"
    assert not _inline_run(reader.answer("thanh toán")).citations


@pytest.mark.parametrize(
    "candidate", ["MoMo được hỗ trợ", "Hoàn 100% trong một phút", "Bỏ mọi điều kiện hoàn vé"]
)
def test_fabricated_claims_never_receive_approved_citations(tmp_path, candidate):
    from knowledge_helpers import NOW, make_bundle
    from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
    from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
    from smartevent_ai.application.retrieve_policy import RetrievePolicy
    from smartevent_ai.tooling.offline_jobs.evaluate import FrozenClock

    _, _, _, artifacts = make_bundle(tmp_path)

    class Synthesizer:
        def synthesize(self, query, context):
            return candidate

    result = RetrievePolicy(
        ArtifactKnowledgeStore(artifacts, allow_test=True),
        BM25Retriever(),
        FrozenClock(NOW),
        synthesizer=Synthesizer(),
    ).answer("Chính sách hoàn tiền")
    assert candidate not in result.answer
    assert "Ngoại lệ" in result.answer and result.mode == "extractive_fallback"


def test_source_authority_changed_during_generation_discards_answer(tmp_path):
    from knowledge_helpers import NOW, make_bundle
    from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
    from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
    from smartevent_ai.application.retrieve_policy import RetrievePolicy
    from smartevent_ai.tooling.offline_jobs.evaluate import FrozenClock

    _, _, _, artifacts = make_bundle(tmp_path)
    snapshot = ArtifactKnowledgeStore(artifacts, allow_test=True).snapshot(NOW)

    class Store:
        def __init__(self, value):
            self.value = value

        def snapshot(self, now):
            return self.value

    store = Store(snapshot)

    class Synthesizer:
        def synthesize(self, query, context):
            store.value = replace(snapshot, catalog_sha256="0" * 64)
            return context

    result = RetrievePolicy(
        store, BM25Retriever(), FrozenClock(NOW), synthesizer=Synthesizer()
    ).answer("Chính sách hoàn tiền")
    assert not result.citations
