"""PEFT LoRA Transformer NLU adapter for SmartEvent.

Translates user utterances into typed domain Understanding using a fine-tuned
Qwen LoRA model. Adheres strictly to the READ_ONLY boundary and falls back
gracefully to deterministic rules upon any model, JSON or range violation.
"""

from __future__ import annotations

import json
import logging
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
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._generator is not None or self._model is not None:
            return
        if self._adapter_path is None or not self._adapter_path.exists():
            raise FileNotFoundError(f"Adapter path not found: {self._adapter_path}")

        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._tokenizer = AutoTokenizer.from_pretrained(
            str(self._adapter_path), trust_remote_code=True
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        quant_config = None
        if torch.cuda.is_available() and self._load_4bit:
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )

        base = AutoModelForCausalLM.from_pretrained(
            self._base_model_name,
            quantization_config=quant_config,
            device_map="auto" if torch.cuda.is_available() else "cpu",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            trust_remote_code=True,
        )
        self._model = PeftModel.from_pretrained(base, str(self._adapter_path))
        self._model.eval()

    def _generate(self, user_text: str) -> str:
        if self._generator is not None:
            return self._generator(user_text)

        self._ensure_loaded()
        assert self._tokenizer is not None and self._model is not None

        import torch

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)

        with torch.no_grad():
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
            raw_response = self._generate(text)
            clean_str = self._clean_json_str(raw_response)
            payload: dict[str, Any] = json.loads(clean_str)

            # Intent extraction
            raw_intent = payload.get("primary_intent", "")
            try:
                intent = Intent(raw_intent)
            except ValueError:
                # Map or fallback if intent is unknown in domain enum
                intent = Intent.OUT_OF_SCOPE

            entities: dict[str, Any] = payload.get("entities") or {}

            # Quantity extraction and range guard
            quantity = entities.get("quantity")
            if quantity is not None:
                try:
                    qty_int = int(quantity)
                    if not (1 <= qty_int <= 20):
                        return Understanding(
                            intent=intent if intent != Intent.OUT_OF_SCOPE else Intent.TICKET_RECOMMEND,
                            needs_clarification=True,
                            clarification_reason=ClarificationReason.QUANTITY_OUT_OF_RANGE,
                        )
                    quantity = qty_int
                except (ValueError, TypeError):
                    quantity = None

            # City normalization
            city = self._normalize_city(entities.get("city"))

            # Budget extraction
            budget_amount = entities.get("budget_amount")
            if budget_amount is not None:
                try:
                    b_int = int(budget_amount)
                    if not (0 <= b_int <= MAX_BUDGET_VND):
                        return Understanding(
                            intent=intent,
                            needs_clarification=True,
                            clarification_reason=ClarificationReason.BUDGET_OUT_OF_RANGE,
                        )
                    budget_amount = b_int
                except (ValueError, TypeError):
                    budget_amount = None

            budget_scope = Scope.UNKNOWN
            raw_scope = entities.get("budget_scope")
            if raw_scope in (Scope.TOTAL, Scope.PER_TICKET):
                budget_scope = Scope(raw_scope)

            # Proposed action and READ_ONLY safety gate
            proposed_action = payload.get("proposed_action", "")
            if proposed_action == "EXPLAIN_WRITE_LIMITATION" or "giữ vé" in text.lower():
                intent = Intent.BOOKING_GUIDANCE

            search_query = entities.get("search_query") or entities.get("event_name")
            if intent is Intent.SEARCH_EVENT and not search_query:
                # If search query not captured in entities, check category or preserve
                search_query = entities.get("category")

            patch = DialoguePatch(
                city=city,
                quantity=quantity,
                budget_amount=budget_amount,
                budget_scope=budget_scope if budget_amount is not None else None,
                event_name=entities.get("event_name"),
                search_query=search_query,
            )
            return Understanding(intent=intent, patch=patch)

        except Exception as e:
            logger.warning(
                "PeftTransformerNLU generation/parsing failed (%s); falling back to RuleBasedNLU",
                e,
            )
            return self._fallback_nlu.parse(text, state)
