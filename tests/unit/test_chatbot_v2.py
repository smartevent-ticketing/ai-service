"""Cross-boundary regressions for the R2 contract; no live approvals are implied."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import asyncio
import pytest
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.adapters.outbound.model_understanding import parse_model_understanding
from smartevent_ai.adapters.inbound.http_api import DialogueStateDTO, ChatResponseDTO, create_app
from smartevent_ai.domain.dialogue import DialogueState, Intent, Scope, Slot, merge_state
from smartevent_ai.domain.search import EventSearchCriteria
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand, EventCard
from smartevent_ai.domain.errors import ContractViolation
from smartevent_ai.infrastructure.settings import Settings
from fastapi.testclient import TestClient

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("message,keyword", [
    ("Tìm sự kiện tháng 11/2026", None),
    ("Tìm sự kiện trong tháng 11", None),
    ("Tìm concert vào tháng 11-2026", "concert"),
    ("Tìm sự kiện tháng sau", None),
    ("Tìm show 2026 trong tháng 11", "show 2026"),
])
def test_month_filter_is_not_sent_as_a_title_keyword(message, keyword):
    result = RuleBasedVietnameseNLU(lambda: NOW).parse(message, DialogueState())
    assert result.patch.start_from is not None
    assert result.patch.search_query == keyword


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
    assert args["startFrom"] == "2026-10-31T17:00:00Z"
    assert args["startBefore"] == "2026-11-30T17:00:00Z"
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
    with pytest.raises(ContractViolation):
        EventCard.from_projection({**row, "slug": "../admin"})
    with pytest.raises(ContractViolation):
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


@pytest.mark.parametrize(
    "status,payload", [(503, b"{}"), (200, b"x" * 65537)], ids=["status_503", "oversized"]
)
def test_remote_reader_distinguishes_knowledge_failure_and_bounds_body(
    monkeypatch, status, payload
):
    from smartevent_ai.adapters.outbound.knowledge import http_reader
    from smartevent_ai.domain.errors import KnowledgeUnavailable

    class Response:
        status_code = status
        headers = {"content-type": "application/json"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_bytes(self):
            yield payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, path, **kwargs):
            assert method == "GET" and path == "/v1/policy"
            return Response()

    monkeypatch.setattr(http_reader.httpx, "AsyncClient", lambda **kwargs: Client())
    reader = http_reader.HttpPolicyReader("http://knowledge:8010", "TEST_ONLY_" * 4)
    with pytest.raises(KnowledgeUnavailable):
        _inline_run(reader.answer("thanh toán"))
    assert reader.status() == "unavailable"


def test_remote_reader_preserves_explicit_degraded_bm25_mode(monkeypatch):
    import json
    from smartevent_ai.adapters.outbound.knowledge import http_reader

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_bytes(self):
            yield json.dumps(
                {"answer": "No evidence", "citations": [], "mode": "degraded_bm25"}
            ).encode()

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(http_reader.httpx, "AsyncClient", lambda **kwargs: Client())
    reader = http_reader.HttpPolicyReader("http://knowledge:8010", "TEST_ONLY_" * 4)
    assert _inline_run(reader.answer("payment")).mode == "degraded_bm25"
    assert reader.status() == "last_read_degraded"


def test_remote_reader_parses_valid_citations(monkeypatch):
    import json
    from smartevent_ai.adapters.outbound.knowledge import http_reader

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_bytes(self):
            yield json.dumps(
                {
                    "answer": "Chính sách hoàn tiền",
                    "citations": [
                        {
                            "source_id": "TEST-REFUND",
                            "version": "1.0.0",
                            "title": "Refund Policy",
                            "canonical_uri": "https://example.com/refund",
                            "chunk_id": "c1",
                            "heading_path": ["Mục 1", "Điều 1"],
                            "start": 0,
                            "end": 100,
                        }
                    ],
                    "mode": "remote_extractive",
                }
            ).encode()

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(http_reader.httpx, "AsyncClient", lambda **kwargs: Client())
    reader = http_reader.HttpPolicyReader("http://knowledge:8010", "TEST_ONLY_" * 4)
    ans = _inline_run(reader.answer("payment"))
    assert ans.mode == "remote_extractive"
    assert len(ans.citations) == 1
    assert ans.citations[0].source_id == "TEST-REFUND"
    assert reader.status() == "last_read_ok"


def test_model_remove_delta_overrides_entities():
    state = DialogueState(city="Hà Nội")
    delta = [{"op": "REMOVE", "slot": "city"}]
    payload = {
        "primary_intent": "SEARCH_EVENT",
        "entities": {"city": "Hà Nội"},
        "state_delta": delta,
    }
    result = parse_model_understanding(payload, state)
    merged = merge_state(state, result.patch)
    assert merged.city is None


def test_rule_nlu_bo_thang_removes_date_filter():
    nlu = RuleBasedVietnameseNLU(lambda: NOW)
    initial = nlu.parse("Tìm sự kiện tháng 11", DialogueState())
    state = merge_state(DialogueState(), initial.patch)
    assert state.start_from is not None

    removed = nlu.parse("bỏ tháng 11", state)
    merged = merge_state(state, removed.patch)
    assert merged.start_from is None and merged.start_before is None
    assert Slot.START_FROM in removed.patch.removed_slots


def test_rule_nlu_budget_followup_preserves_search_query():
    nlu = RuleBasedVietnameseNLU(lambda: NOW)
    first = nlu.parse("Tìm concert Blackpink", DialogueState())
    state = merge_state(DialogueState(), first.patch)
    assert state.search_query == "concert blackpink"

    second = nlu.parse("dưới 500k mỗi vé", state)
    merged = merge_state(state, second.patch)
    assert merged.search_query == "concert blackpink"
    assert merged.budget_amount == 500000


def test_rule_nlu_city_negation_compound_prefix():
    nlu = RuleBasedVietnameseNLU(lambda: NOW)
    state = DialogueState(city="Hồ Chí Minh", active_intent=Intent.SEARCH_EVENT)

    parsed_khong_o = nlu.parse("không ở tp.hcm", state)
    merged1 = merge_state(state, parsed_khong_o.patch)
    assert merged1.city is None

    parsed_bo = nlu.parse("bỏ tp.hcm", state)
    merged2 = merge_state(state, parsed_bo.patch)
    assert merged2.city is None


def test_rule_nlu_refund_policy_followup():
    nlu = RuleBasedVietnameseNLU(lambda: NOW)
    first = nlu.parse("Chính sách hoàn tiền thế nào?", DialogueState())
    assert first.intent is Intent.REFUND_POLICY
    state = merge_state(DialogueState(), first.patch)

    second = nlu.parse("Còn thời hạn bao lâu?", state)
    assert second.intent in (Intent.REFUND_POLICY, Intent.POLICY_FAQ)


def test_event_card_city_length_and_empty_string_handling():
    base = {
        "id": str(uuid4()),
        "name": "Live Concert",
        "slug": "live-concert",
    }
    # 90 characters city is valid (max 100)
    long_city = "A" * 90
    card1 = EventCard.from_projection({**base, "city": long_city})
    assert card1.city == long_city

    # > 100 characters city raises ContractViolation
    with pytest.raises(ContractViolation):
        EventCard.from_projection({**base, "city": "A" * 101})

    # Empty string treated as None
    card_empty = EventCard.from_projection({**base, "city": "", "venueName": ""})
    assert card_empty.city is None
    assert card_empty.venue_name is None


def test_ready_probe_with_model_backend_not_permanently_degraded():
    from smartevent_ai.application.ports import BusinessReadTools

    class MockTools(BusinessReadTools):
        def available_names(self):
            return ["search_events"]

        def capabilities(self):
            return {"search_events": {}}

        async def execute(self, name, arguments):
            return {"data": []}

    app = create_app(Settings(nlu_backend="ollama", _env_file=None))
    app.state.gateway = MockTools()

    with TestClient(app) as client:
        ready = client.get("/health/ready").json()
        assert ready["status"] == "ready"
        assert ready["model_backend"] == "ollama"
