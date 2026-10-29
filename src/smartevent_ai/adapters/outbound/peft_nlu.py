"""PEFT LoRA Transformer NLU adapter for SmartEvent.

Translates user utterances into typed domain Understanding using a fine-tuned
Qwen LoRA model. Adheres strictly to the READ_ONLY boundary and falls back
gracefully to deterministic rules upon any model, JSON or range violation.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from smartevent_ai.adapters.outbound.rule_nlu import CITY_ALIASES, RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import (
    MAX_BUDGET_VND,
    ClarificationReason,
    DialoguePatch,
    DialogueState,
    Intent,
    Scope,
    Slot,
    Understanding,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là bộ phân tích NLU SmartEvent v1.2. Nhiệm vụ: Phân tích tin nhắn và xuất DUY NHẤT một khối JSON chứa:\n"
    "- primary_intent: Intent phù hợp (SEARCH_EVENT, TICKET_RECOMMEND, BOOKING_GUIDANCE, REFUND_POLICY, ORDER_STATUS, MY_TICKETS, GREETING, ...)\n"
    "- proposed_action: Hành động chỉ đọc (SEARCH_EVENTS, RUN_TICKET_OPTIMIZER, EXPLAIN_WRITE_LIMITATION, RETRIEVE_POLICY, ...)\n"
    "- entities: dict các thực thể (city, quantity, ticket_type_name, ...)\n"
    "- state_delta: danh sách các thao tác cập nhật trạng thái nếu có.\n"
    "TUYỆT ĐỐI không đề xuất hành động ghi dữ liệu. Xuất JSON hợp lệ."
)


class PeftTransformerNLU:
    """NLU adapter powered by fine-tuned LoRA SLM with zero-crash rule fallback."""

    def __init__(
        self,
        adapter_path: Path | str | None = None,
        base_model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
        load_4bit: bool = True,
        generator: Callable[[str], str] | None = None,
    ) -> None:
        self._adapter_path = Path(adapter_path) if adapter_path is not None else None
        self._base_model_name = base_model_name
        self._load_4bit = load_4bit
        self._generator = generator
        self._fallback_nlu = RuleBasedVietnameseNLU()
        self._model: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._generator is not None or self._model is not None:
            return
        with self._lock:
            if self._generator is not None or self._model is not None:
                return
            if self._adapter_path is None or not self._adapter_path.exists():
                raise FileNotFoundError(f"Adapter path not found: {self._adapter_path}")

            import torch as _torch  # type: ignore[import-untyped]
            torch_any: Any = _torch
            from peft import PeftModel  # type: ignore[import-not-found]
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            tokenizer_source = str(self._adapter_path)
            has_tokenizer_config = (
                (self._adapter_path / "tokenizer_config.json").exists()
                or (self._adapter_path / "tokenizer.json").exists()
            )
            if not has_tokenizer_config:
                logger.info(
                    "Tokenizer config not found in %s; falling back to base model %s",
                    self._adapter_path,
                    self._base_model_name,
                )
                tokenizer_source = self._base_model_name

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    tokenizer_source, trust_remote_code=True
                )
            except Exception as e:
                if tokenizer_source != self._base_model_name:
                    logger.warning(
                        "Failed loading tokenizer from %s (%s); falling back to base model %s",
                        tokenizer_source,
                        e,
                        self._base_model_name,
                    )
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        self._base_model_name, trust_remote_code=True
                    )
                else:
                    raise

            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

            quant_config = None
            if torch_any.cuda.is_available() and self._load_4bit:
                quant_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch_any.float16,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )

            base = AutoModelForCausalLM.from_pretrained(
                self._base_model_name,
                quantization_config=quant_config,
                device_map="auto" if torch_any.cuda.is_available() else "cpu",
                torch_dtype=torch_any.float16 if torch_any.cuda.is_available() else torch_any.float32,
                trust_remote_code=True,
            )
            self._model = PeftModel.from_pretrained(base, str(self._adapter_path))
            self._model.eval()

    def _generate(self, user_text: str, state: DialogueState | None = None) -> str:
        user_content = user_text
        if state is not None and (
            state.active_intent is not None
            or state.city
            or state.quantity
            or state.budget_amount is not None
            or state.event_name
            or state.search_query
        ):
            context_parts = []
            if state.active_intent:
                context_parts.append(f"active_intent: {state.active_intent.value}")
            if state.city:
                context_parts.append(f"city: {state.city}")
            if state.quantity:
                context_parts.append(f"quantity: {state.quantity}")
            if state.budget_amount is not None:
                context_parts.append(f"budget_amount: {state.budget_amount}")
            if state.budget_scope and state.budget_scope is not Scope.UNKNOWN:
                context_parts.append(f"budget_scope: {state.budget_scope.value}")
            if state.event_name:
                context_parts.append(f"event_name: {state.event_name}")
            if state.search_query:
                context_parts.append(f"search_query: {state.search_query}")
            user_content = (
                f"Trạng thái trước:\n{{{', '.join(context_parts)}}}\n\n"
                f"Tin nhắn người dùng: {user_text}"
            )

        if self._generator is not None:
            return self._generator(user_content)

        self._ensure_loaded()
        assert self._tokenizer is not None and self._model is not None

        import torch as _torch
        torch_any: Any = _torch

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)

        with self._lock:
            with torch_any.no_grad():
                output_tokens = self._model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id,
                )
        prompt_len = inputs["input_ids"].shape[1]
        gen_tokens = output_tokens[0][prompt_len:]
        return self._tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

    def _clean_json_str(self, raw: str) -> str:
        s = raw.strip()
        if s.startswith("```"):
            lines = s.split("\n")
            s = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return s.strip()

    def _normalize_city(self, city: str | None) -> str | None:
        if not city:
            return None
        norm = city.strip().casefold()
        for marker, canonical in CITY_ALIASES:
            if marker in norm or norm in marker:
                return canonical
        return city.strip()

    def parse(self, text: str, state: DialogueState) -> Understanding:
        try:
            raw_response = self._generate(text, state)
            clean_str = self._clean_json_str(raw_response)
            payload: dict[str, Any] = json.loads(clean_str)

            # Intent extraction with case-insensitivity
            raw_intent = str(payload.get("primary_intent", "")).strip().upper()
            try:
                intent = Intent(raw_intent)
            except ValueError:
                intent = Intent.OUT_OF_SCOPE

            entities: dict[str, Any] = payload.get("entities") or {}

            # City normalization
            city = self._normalize_city(entities.get("city"))

            # Search query
            search_query = entities.get("search_query") or entities.get("event_name")
            if intent is Intent.SEARCH_EVENT and not search_query:
                search_query = entities.get("category")

            # Quantity extraction and range guard
            quantity = entities.get("quantity")
            if quantity is not None:
                try:
                    qty_int = int(quantity)
                    if not (1 <= qty_int <= 20):
                        return Understanding(
                            intent=intent
                            if intent != Intent.OUT_OF_SCOPE
                            else Intent.TICKET_RECOMMEND,
                            patch=DialoguePatch(
                                city=city,
                                event_name=entities.get("event_name"),
                                search_query=search_query,
                                active_intent=intent,
                            ),
                            needs_clarification=True,
                            clarification_reason=ClarificationReason.QUANTITY_OUT_OF_RANGE,
                        )
                    quantity = qty_int
                except (ValueError, TypeError):
                    quantity = None

            # Budget extraction
            budget_amount = entities.get("budget_amount")
            if budget_amount is not None:
                try:
                    b_int = int(budget_amount)
                    if not (0 <= b_int <= MAX_BUDGET_VND):
                        return Understanding(
                            intent=intent,
                            patch=DialoguePatch(
                                city=city,
                                quantity=quantity,
                                event_name=entities.get("event_name"),
                                search_query=search_query,
                                active_intent=intent,
                            ),
                            needs_clarification=True,
                            clarification_reason=ClarificationReason.BUDGET_OUT_OF_RANGE,
                        )
                    budget_amount = b_int
                except (ValueError, TypeError):
                    budget_amount = None

            budget_scope = Scope.UNKNOWN
            raw_scope = entities.get("budget_scope")
            if raw_scope is not None:
                raw_scope = str(raw_scope).strip().upper()
            if raw_scope in (Scope.TOTAL, Scope.PER_TICKET):
                budget_scope = Scope(raw_scope)

            # Proposed action and READ_ONLY safety gate
            proposed_action = payload.get("proposed_action", "")
            if proposed_action == "EXPLAIN_WRITE_LIMITATION" or "giữ vé" in text.lower():
                intent = Intent.BOOKING_GUIDANCE

            removed_slots: set[Slot] = set()
            if budget_amount is not None:
                resolved_scope = budget_scope
                if budget_scope is Scope.UNKNOWN and state.budget_scope is not Scope.UNKNOWN:
                    removed_slots.add(Slot.BUDGET_SCOPE)
            elif state.budget_amount is not None and budget_scope is not Scope.UNKNOWN:
                resolved_scope = budget_scope
            else:
                resolved_scope = None

            patch = DialoguePatch(
                city=city,
                quantity=quantity,
                budget_amount=budget_amount,
                budget_scope=resolved_scope,
                event_name=entities.get("event_name"),
                search_query=search_query,
                active_intent=intent,
                removed_slots=frozenset(removed_slots),
            )
            return Understanding(intent=intent, patch=patch)

        except Exception as e:
            logger.warning(
                "PeftTransformerNLU generation/parsing failed (%s); falling back to RuleBasedNLU",
                e,
            )
            return self._fallback_nlu.parse(text, state)
