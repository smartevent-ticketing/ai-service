"""Audit regression tests; fixture approvals are never live runtime evidence."""

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import SpyTransport
from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.model_understanding import parse_model_understanding
from smartevent_ai.adapters.outbound.ollama_nlu import OllamaNLU
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import EventCard
from smartevent_ai.domain.dialogue import DialogueState, merge_state
from smartevent_ai.domain.errors import (
    BackendUnavailable,
    ContractViolation,
    ToolUnavailable,
    UpstreamTimeout,
)
from smartevent_ai.domain.knowledge import PolicyAnswer
from smartevent_ai.domain.search import EventSearchCriteria
from smartevent_ai.infrastructure.settings import Settings

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def row():
    return {
        "id": str(uuid4()),
        "name": "Concert",
        "slug": "concert",
        "startTime": "2026-11-01T00:00:00+07:00",
        "endTime": "2026-11-01T15:00:00Z",
        "price": 500000,
        "currency": "VND",
        "ticketTypeId": str(uuid4()),
        "salePhaseId": str(uuid4()),
        "priceObservedAt": "2026-10-30T00:00:00Z",
        "priceBasis": "TICKET_FACE_VALUE",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"id": 1},
        {"id": "not-a-uuid"},
        {"slug": "../admin"},
        {"name": None},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"price": True},
        {"price": {}},
        {"price": "invalid"},
        {"currency": "USD"},
        {"ticketTypeId": []},
        {"salePhaseId": "bad"},
        {"priceObservedAt": "2026-10-30"},
        {"startTime": False},
        {"startTime": "2026-11-02T00:00:00Z"},
        {"city": []},
        {"priceBasis": "UNVERIFIED"},
    ],
)
def test_malformed_card_is_a_typed_contract_error(change):
    with pytest.raises(ContractViolation):
        EventCard.from_projection({**row(), **change})


def test_verified_price_and_route_come_from_projection():
    card = EventCard.from_projection(row())
    assert card.price == "500000" and card.detail_path == "/events/concert"
    assert card.ticket_type_id and card.sale_phase_id


class Tools:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error:
            raise self.error("internal secret URL")
        return self.result


@pytest.mark.parametrize(
    "error,status,code,retryable",
    [
        (BackendUnavailable, 503, "BACKEND_UNAVAILABLE", True),
        (ContractViolation, 502, "UPSTREAM_CONTRACT_ERROR", False),
        (UpstreamTimeout, 504, "UPSTREAM_TIMEOUT", True),
    ],
)
def test_execute_errors_keep_their_taxonomy(error, status, code, retryable):
    app = create_app(Settings(_env_file=None))
    app.state.chat = ChatUseCase(RuleBasedVietnameseNLU(lambda: NOW), Tools(error=error))
    with TestClient(app) as api:
        response = api.post("/api/v1/chat", json={"message": "Tìm concert"})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["retryable"] is retryable
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"data": None},
        {"data": {}},
        {"data": [None]},
        {"data": [{"id": 1}]},
        {"data": [], "has_more": "false"},
    ],
)
def test_projection_errors_match_execute_contract_errors(result):
    app = create_app(Settings(_env_file=None))
    app.state.chat = ChatUseCase(RuleBasedVietnameseNLU(lambda: NOW), Tools(result=result))
    with TestClient(app) as api:
        response = api.post("/api/v1/chat", json={"message": "Tìm concert"})
    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM_CONTRACT_ERROR"


def test_disabled_tool_still_returns_conversation_fallback():
    app = create_app(Settings(_env_file=None))
    app.state.chat = ChatUseCase(RuleBasedVietnameseNLU(lambda: NOW), Tools(error=ToolUnavailable))
    with TestClient(app) as api:
        response = api.post("/api/v1/chat", json={"message": "Tìm concert"})
    assert response.status_code == 200 and response.json()["status"] == "TOOL_DISABLED"


def test_utc_serialization_keeps_subsecond_precision():
    local = datetime.fromisoformat("2026-11-01T00:00:00.123456+07:00")
    args = EventSearchCriteria(start_from=local).as_tool_arguments()
    assert args["startFrom"] == "2026-10-31T17:00:00.123456Z"
    assert (
        EventSearchCriteria(start_from=local.astimezone(timezone.utc)).as_tool_arguments() == args
    )
    with pytest.raises(ValueError):
        EventSearchCriteria(start_from=local.replace(tzinfo=None))


@pytest.mark.parametrize("entities", [[], False, "", 0])
def test_falsey_non_object_entities_are_rejected(entities):
    with pytest.raises(ValueError):
        parse_model_understanding(
            {"primary_intent": "SEARCH_EVENT", "entities": entities}, DialogueState()
        )


@pytest.mark.parametrize("reverse", [False, True])
def test_set_wins_after_remove_independent_of_operation_order(reverse):
    operations = [
        {"op": "SET", "slot": "city", "value": "Hà Nội"},
        {"op": "REMOVE", "slot": "city"},
    ]
    result = parse_model_understanding(
        {
            "primary_intent": "SEARCH_EVENT",
            "state_delta": list(reversed(operations)) if reverse else operations,
        },
        DialogueState(city="Huế"),
    )
    assert merge_state(DialogueState(city="Huế"), result.patch).city == "Hà Nội"


@pytest.mark.parametrize("city", ["hcmville", "huehue"])
def test_city_alias_does_not_match_substrings(city):
    result = parse_model_understanding(
        {"primary_intent": "SEARCH_EVENT", "entities": {"city": city}}, DialogueState()
    )
    assert result.patch.city == city
    assert RuleBasedVietnameseNLU().parse("Tìm concert " + city, DialogueState()).patch.city is None


def test_both_model_adapters_share_clock_and_full_filter_context():
    prompts = []

    def handler(request):
        import json

        prompts.append(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200, json={"message": {"content": '{"primary_intent":"SEARCH_EVENT"}'}}
        )

    ollama = OllamaNLU(client=httpx.Client(transport=httpx.MockTransport(handler)), now=lambda: NOW)

    def generate(prompt):
        prompts.append(prompt)
        return '{"primary_intent":"SEARCH_EVENT"}'

    peft = PeftTransformerNLU(generator=generate, now=lambda: NOW)
    state = DialogueState(start_from=NOW, faq_topic="thanh toán")
    for adapter in (ollama, peft):
        adapter.parse("Tìm concert", state)
    for prompt in prompts:
        assert "2026-10-30T07:00:00+07:00" in prompt
        assert "start_from:" in prompt and "faq_topic:" in prompt
    ollama.close()


class Policies:
    def __init__(self):
        self.queries = []

    async def answer(self, query):
        self.queries.append(query)
        return PolicyAnswer("Chưa đủ nguồn")

    def status(self):
        return "disabled"


def test_faq_followup_private_boundary_and_new_search_isolation():
    policies, tools = Policies(), Tools(result={"data": []})
    app = create_app(Settings(_env_file=None))
    app.state.chat = ChatUseCase(RuleBasedVietnameseNLU(lambda: NOW), tools, policies=policies)
    with TestClient(app) as api:
        first = api.post("/api/v1/chat", json={"message": "Thanh toán thế nào?"}).json()
        assert first["state"]["faq_topic"] == "thanh toán"
        api.post("/api/v1/chat", json={"message": "Còn VNPay?", "previous_state": first["state"]})
        assert policies.queries[-1] == "thanh toán: Còn VNPay?"
        api.post(
            "/api/v1/chat",
            json={
                "message": "Còn trạng thái thanh toán của tôi?",
                "previous_state": first["state"],
            },
        )
        assert len(policies.queries) == 2
        state = {
            **first["state"],
            "budget_amount": 1000,
            "budget_scope": "PER_TICKET",
            "city": "Huế",
        }
        result = api.post(
            "/api/v1/chat", json={"message": "Tìm concert ở Hà Nội", "previous_state": state}
        ).json()
        assert result["state"]["budget_amount"] is None and result["state"]["faq_topic"] is None
        assert tools.calls[-1][1] == {"q": "concert", "city": "Hà Nội", "page": 0, "size": 10}


def test_readiness_reports_blocked_filter_capability(approved_registry):
    registry, gates_path = approved_registry
    gateway = ReadOnlyToolGateway(registry, gates_path, SpyTransport())
    assert gateway.capabilities()["search_events"] == {
        "available": True,
        "date_price_filters": False,
    }
    gates = yaml.safe_load(gates_path.read_text())
    gates["gates"]["PUBLISHED-CHILD"]["status"] = "PASS"
    gates_path.write_text(yaml.safe_dump(gates))
    gateway = ReadOnlyToolGateway(registry, gates_path, SpyTransport())
    assert gateway.capabilities()["search_events"]["date_price_filters"]


def test_readiness_does_not_treat_last_request_as_model_probe():
    app = create_app(Settings(nlu_backend="ollama", _env_file=None))
    with TestClient(app) as api:
        before = api.get("/health/ready").json()
        app.state.chat.last_nlu_mode = "model"
        after = api.get("/health/ready").json()
    assert before["status"] == after["status"] == "degraded"
    assert after["nlu_availability"] == "unverified"


def test_invalid_request_uses_safe_error_envelope():
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as api:
        response = api.post("/api/v1/chat", json={"message": "", "secret": "DO_NOT_ECHO"})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "DO_NOT_ECHO" not in response.text
