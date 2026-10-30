import json

import httpx
import pytest

from smartevent_ai.adapters.outbound.llama_cpp import (
    LlamaCppNLU,
    LlamaCppPolicySynthesizer,
    content,
)
from smartevent_ai.domain.dialogue import DialogueState, Intent
from smartevent_ai.domain.dialogue import Scope, merge_state
from smartevent_ai.adapters.outbound.llama_cpp import OllamaCheckpointNLU
from smartevent_ai.infrastructure.bootstrap import build_chat
from smartevent_ai.infrastructure.settings import Settings


def test_nlu_fixed_endpoint_schema_and_shared_strict_parser():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["max_tokens"] == 256
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"primary_intent": "SEARCH_EVENT", "entities": {"city": "Hà Nội"}}
                            )
                        }
                    }
                ]
            },
        )

    nlu = LlamaCppNLU(client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = nlu.parse("Tìm sự kiện ở Hà Nội", DialogueState())
    assert result.intent is Intent.SEARCH_EVENT and result.patch.city == "Hà Nội"
    assert result.mode == "model"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [2]},
        {"choices": [{"message": "invalid"}]},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_malformed_provider_response_cannot_be_treated_as_model_success(payload):
    with pytest.raises(ValueError):
        content(payload)


def test_rag_adapter_returns_text_for_existing_evidence_verifier():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "TEST_ONLY source extract"}}]}
        )

    adapter = LlamaCppPolicySynthesizer(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert adapter.synthesize("test", "TEST_ONLY source extract") == "TEST_ONLY source extract"


@pytest.mark.parametrize("message", ["mỗi vé", "Đổi sang Hà Nội", "bỏ giới hạn giá"])
def test_checkpoint_followup_changes_conditions_without_inventing_an_answer(message):
    def handler(request):
        pytest.fail("Mechanical followup must not require model generation")

    adapter = OllamaCheckpointNLU(
        checkpoint_contract=True, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    state = DialogueState(
        active_intent=Intent.SEARCH_EVENT, city="Hồ Chí Minh", budget_amount=500000
    )
    result = adapter.parse(message, state)
    updated = merge_state(state, result.patch)
    assert result.mode == "rule_followup" and result.intent is Intent.SEARCH_EVENT
    if message == "mỗi vé":
        assert updated.budget_scope is Scope.PER_TICKET
    elif message == "Đổi sang Hà Nội":
        assert updated.city == "Hà Nội" and updated.budget_amount == 500000
    else:
        assert updated.budget_amount is None


def test_checkpoint_provider_is_explicitly_selected_in_composition():
    chat, _ = build_chat(
        Settings(nlu_backend="ollama", nlu_contract="checkpoint_v1_2", _env_file=None)
    )
    assert isinstance(chat._nlu, OllamaCheckpointNLU)
