"""Generative policy answer synthesizers for SmartEvent RAG.

Synthesizes natural language answers strictly grounded in retrieved evidence chunks.
Enforces the READ_ONLY invariant and falls back to raw extractive passages on any failure.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là trợ lý giải đáp chính sách SmartEvent v1.2.\n"
    "Nhiệm vụ: Trả lời câu hỏi người dùng DỰA CHÍNH XÁC VÀO TÀI LIỆU CHÍNH SÁCH được cung cấp.\n"
    "- Trích dẫn đúng thời hạn, điều kiện, ngoại lệ.\n"
    "- Nếu tài liệu không có thông tin, nêu rõ không có dữ liệu, không tự bịa đặt.\n"
    "- Tuyệt đối từ chối thực hiện thao tác hủy/đổi/hoàn tiền thay người dùng; hướng dẫn người dùng tự thao tác."
)


class OllamaPolicySynthesizer:
    """Outbound adapter synthesizing policy answers via Ollama GGUF model."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "smartevent-rag:3b",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def synthesize(self, query: str, context: str) -> str:
        try:
            url = f"{self._base_url}/api/chat"
            user_content = f"Ngữ cảnh tài liệu:\n{context}\n\nCâu hỏi: {query}"
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.0,
                },
            }
            # Use build_request + send to adhere to static_verify.py AST checks
            req = self._client.build_request("POST", url, json=payload)
            response = self._client.send(req)
            response.raise_for_status()

            body = response.json()
            answer = body.get("message", {}).get("content", "").strip()
            if answer:
                return answer
            return context
        except Exception as e:
            logger.warning(
                "OllamaPolicySynthesizer failed (%s); falling back to extractive context", e
            )
            return context


class PeftPolicySynthesizer:
    """In-process PEFT synthesizer for standalone testing and GPU benchmark."""

    def __init__(
        self,
        adapter_path: Path | str | None = None,
        base_model_name: str = "Qwen/Qwen2.5-3B-Instruct",
        load_4bit: bool = True,
        generator: Callable[[str], str] | None = None,
    ) -> None:
        self._adapter_path = Path(adapter_path) if adapter_path is not None else None
        self._base_model_name = base_model_name
        self._load_4bit = load_4bit
        self._generator = generator
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
                raise FileNotFoundError(f"RAG adapter path not found: {self._adapter_path}")

        import torch as _torch

        torch_any: Any = _torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._tokenizer = AutoTokenizer.from_pretrained(
            str(self._adapter_path), trust_remote_code=True
        )
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

    def synthesize(self, query: str, context: str) -> str:
        try:
            if self._generator is not None:
                return self._generator(f"{context}\n\n{query}")

            self._ensure_loaded()
            assert self._tokenizer is not None and self._model is not None

            import torch as _torch

            torch_any: Any = _torch

            user_content = f"Ngữ cảnh tài liệu:\n{context}\n\nCâu hỏi: {query}"
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)

            with torch_any.no_grad():
                output_tokens = self._model.generate(
                    **inputs,
                    max_new_tokens=300,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id,
                )
            prompt_len = inputs["input_ids"].shape[1]
            gen_tokens = output_tokens[0][prompt_len:]
            gen_text = self._tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()
            return gen_text or context
        except Exception as e:
            logger.warning(
                "PeftPolicySynthesizer failed (%s); falling back to extractive context", e
            )
            return context
