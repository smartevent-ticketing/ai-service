"""Fixed llama.cpp inference adapters for project GGUF LoRA checkpoints."""

from typing import Any
from dataclasses import replace

from smartevent_ai.adapters.outbound.ollama_nlu import OllamaNLU
from smartevent_ai.adapters.outbound.legacy_checkpoint import (
    TRAINING_PROMPT,
    adapt_checkpoint,
    folded,
)
from smartevent_ai.domain.dialogue import DialogueState, Intent, Understanding
from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import (
    OllamaPolicySynthesizer,
    SYSTEM_PROMPT,
)


def content(body: Any) -> str:
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("choices"), list)
        or not body["choices"]
    ):
        raise ValueError("Invalid model response")
    choice = body["choices"][0]
    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
        raise ValueError("Invalid model message")
    value = choice["message"].get("content")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing model content")
    return value


class LlamaCppNLU(OllamaNLU):
    def __init__(self, *args: Any, checkpoint_contract: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._checkpoint_contract = checkpoint_contract

    def parse(self, text: str, state: DialogueState) -> Understanding:
        if self._checkpoint_contract and state.active_intent in (
            Intent.SEARCH_EVENT,
            Intent.TICKET_RECOMMEND,
        ):
            rule = self._fallback_nlu.parse(text, state)
            short = folded(text.strip())
            if rule.intent is Intent.SEARCH_EVENT and (
                rule.patch.removed_slots
                or rule.patch.clear_group
                or short in ("moi ve", "1 ve", "mot ve", "tong", "tong tat ca ve")
                or (short.startswith(("doi sang ", "chuyen sang ")) and rule.patch.city)
            ):
                return replace(rule, mode="rule_followup")
        return super().parse(text, state)

    def _prepare_request(self, url: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        messages = payload["messages"]
        if self._checkpoint_contract:
            user = messages[-1]["content"]
            if user.startswith("Đồng hồ tham chiếu"):
                user = user.split("\n", 1)[1]
            messages = [
                {"role": "system", "content": TRAINING_PROMPT},
                {"role": "user", "content": user},
            ]
        return self._base_url + "/v1/chat/completions", {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "temperature": 0.0,
            "max_tokens": 256,
            "response_format": {"type": "json_object"}
            if self._checkpoint_contract
            else {
                "type": "json_schema",
                "json_schema": {"name": "understanding", "schema": payload["format"]},
            },
        }

    def _response_content(self, body: Any) -> str:
        return content(body)

    def _understanding_payload(self, raw: str, text: str, state: DialogueState) -> dict[str, Any]:
        if self._checkpoint_contract:
            return adapt_checkpoint(raw, text, state, self._fallback_nlu)
        return super()._understanding_payload(raw, text, state)


class LlamaCppPolicySynthesizer(OllamaPolicySynthesizer):
    def synthesize(self, query: str, context: str) -> str:
        request = self._client.build_request(
            "POST",
            self._base_url + "/v1/chat/completions",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Ngữ cảnh tài liệu:\n{context}\n\nCâu hỏi: {query}",
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 256,
                "stream": False,
            },
        )
        response = self._client.send(request)
        response.raise_for_status()
        return content(response.json())


class OllamaCheckpointNLU(LlamaCppNLU):
    """The same explicit checkpoint contract over Ollama's native API."""

    def _prepare_request(self, url: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        _, compatible = super()._prepare_request(url, payload)
        return self._base_url + "/api/chat", {
            "model": self._model,
            "messages": compatible["messages"],
            "stream": False,
            "format": "json",
            "keep_alive": -1,
            "options": {"temperature": 0.0, "num_predict": 256, "num_ctx": 2048},
        }

    def _response_content(self, body: Any) -> str:
        return OllamaNLU._response_content(self, body)
