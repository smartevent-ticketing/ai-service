"""In-process orchestration probes. These do not claim HTTP or live integration."""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from starlette.requests import Request

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand
from smartevent_ai.domain.dialogue import DialogueState, Intent
from smartevent_ai.domain.errors import BackendUnavailable, ContractViolation, UpstreamTimeout
from smartevent_ai.domain.knowledge import PolicyAnswer
from smartevent_ai.infrastructure.settings import Settings


def finish(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("Probe unexpectedly attempted external IO")


@pytest.fixture
def inline_scheduler(monkeypatch):
    async def call(function, *args):
        return function(*args)

    async def wait(coroutine, timeout):
        return await coroutine

    monkeypatch.setattr(asyncio, "to_thread", call)
    monkeypatch.setattr(asyncio, "wait_for", wait)


class Tools:
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    async def execute(self, name, arguments):
        self.calls.append(arguments)
        if self.error:
            raise self.error("private dependency detail")
        return self.result


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"data": None},
        {"data": [None]},
        {"data": [{"id": 1}]},
        {"data": [], "has_more": "false"},
    ],
)
def test_bad_projection_fails_at_application_boundary(inline_scheduler, result):
    chat = ChatUseCase(RuleBasedVietnameseNLU(), Tools(result=result))
    with pytest.raises(ContractViolation):
        finish(chat.handle(ChatCommand("Tìm concert")))


@pytest.mark.parametrize(
    "error,status,code",
    [
        (BackendUnavailable, 503, "BACKEND_UNAVAILABLE"),
        (UpstreamTimeout, 504, "UPSTREAM_TIMEOUT"),
        (ContractViolation, 502, "UPSTREAM_CONTRACT_ERROR"),
    ],
)
def test_execute_and_http_error_handler_preserve_taxonomy(inline_scheduler, error, status, code):
    chat = ChatUseCase(RuleBasedVietnameseNLU(), Tools(error=error))
    with pytest.raises(error) as caught:
        finish(chat.handle(ChatCommand("Tìm concert")))
    from smartevent_ai.domain.errors import SmartEventError

    app = create_app(Settings(_env_file=None))
    request = Request({"type": "http", "state": {"request_id": "test-request"}})
    response = finish(app.exception_handlers[SmartEventError](request, caught.value))
    payload = json.loads(response.body)
    assert response.status_code == status and payload["code"] == code
    assert payload["request_id"] == "test-request"
    assert b"private" not in response.body


def test_budget_sequence_preserves_date_and_purges_only_requested_filter(inline_scheduler):
    tools = Tools(result={"data": []})
    chat = ChatUseCase(
        RuleBasedVietnameseNLU(lambda: datetime(2026, 10, 30, tzinfo=timezone.utc)), tools
    )
    first = finish(chat.handle(ChatCommand("Tìm concert ở TP.HCM dưới 500k tháng 11")))
    assert first.status == "CLARIFY" and not tools.calls
    second = finish(chat.handle(ChatCommand("mỗi vé", previous_state=first.state)))
    assert second.status == "EMPTY" and tools.calls[-1]["maxPrice"] == "500000"
    assert tools.calls[-1]["startFrom"] == "2026-10-31T17:00:00Z"
    third = finish(chat.handle(ChatCommand("Đổi sang Hà Nội", previous_state=second.state)))
    assert third.state.start_from == second.state.start_from
    finish(chat.handle(ChatCommand("bỏ giới hạn giá", previous_state=third.state)))
    assert "maxPrice" not in tools.calls[-1] and tools.calls[-1]["city"] == "Hà Nội"


def test_faq_routing_never_uses_corpus_for_account_state(inline_scheduler):
    class Policies:
        queries = []

        async def answer(self, query):
            self.queries.append(query)
            return PolicyAnswer("Chưa đủ nguồn")

    policies = Policies()
    tools = Tools(result={"data": []})
    chat = ChatUseCase(RuleBasedVietnameseNLU(), tools, policies=policies)
    first = finish(chat.handle(ChatCommand("Thanh toán thế nào?")))
    finish(chat.handle(ChatCommand("Còn VNPay?", previous_state=first.state)))
    assert policies.queries[-1] == "thanh toán: Còn VNPay?"
    private = finish(
        chat.handle(ChatCommand("Còn trạng thái thanh toán của tôi?", previous_state=first.state))
    )
    assert private.intent is Intent.PAYMENT_STATUS and len(policies.queries) == 2
    stale = DialogueState(
        active_intent=Intent.PUBLIC_HELP, faq_topic="thanh toán", budget_amount=1000, city="Huế"
    )
    search = finish(chat.handle(ChatCommand("Tìm concert ở Hà Nội", previous_state=stale)))
    assert search.state.budget_amount is None and search.state.faq_topic is None
    assert tools.calls[-1] == {"q": "concert", "city": "Hà Nội", "page": 0, "size": 10}


@pytest.mark.parametrize("verdict", ["raises", "empty"])
def test_evidence_without_judge_verdict_is_not_approved(tmp_path, verdict):
    from knowledge_helpers import NOW, make_bundle
    from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
    from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
    from smartevent_ai.application.retrieve_policy import RetrievePolicy
    from smartevent_ai.tooling.offline_jobs.evaluate import FrozenClock

    _, _, _, artifacts = make_bundle(tmp_path)

    class Judge:
        def judge(self, query, chunks):
            if verdict == "raises":
                raise RuntimeError("judge down")
            return ()

    answer = RetrievePolicy(
        ArtifactKnowledgeStore(artifacts, allow_test=True),
        BM25Retriever(),
        FrozenClock(NOW),
        judge=Judge(),
    ).answer("Chính sách hoàn tiền")
    assert not answer.citations
