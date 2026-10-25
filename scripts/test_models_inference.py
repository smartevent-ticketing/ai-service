"""Inference test script for SmartEvent NLU (1.5B) and RAG (3B) PEFT models.

Strictly follows SmartEvent v1.2 READ_ONLY contract.
Designed for RTX 2050 (4GB VRAM) using 4-bit NF4 quantization.
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def get_vram_mb() -> float:
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / (1024 * 1024)
    return 0.0


def load_model_and_tokenizer(
    base_model_name: str,
    adapter_path: Path,
    use_4bit: bool = True,
):
    print(f"\n[INIT] Loading tokenizer from: {adapter_path}")
    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_path),
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    device_map = "auto" if torch.cuda.is_available() else "cpu"
    print(f"[INIT] Target device: {device_map}")

    quant_config = None
    if torch.cuda.is_available() and use_4bit:
        print("[INIT] Configuring 4-bit NF4 quantization (bitsandbytes)")
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

    print(f"[INIT] Loading base model: {base_model_name}...")
    t0 = time.time()
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        quantization_config=quant_config,
        device_map=device_map,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        trust_remote_code=True,
    )
    print(f"[INIT] Base model loaded in {time.time() - t0:.2f}s | VRAM: {get_vram_mb():.1f}MB")

    print(f"[INIT] Attaching LoRA adapter from: {adapter_path}...")
    t1 = time.time()
    model = PeftModel.from_pretrained(base_model, str(adapter_path))
    model.eval()
    print(f"[INIT] Adapter attached in {time.time() - t1:.2f}s | VRAM: {get_vram_mb():.1f}MB")

    return model, tokenizer


def run_nlu_tests(adapter_path: Path, use_4bit: bool = True):
    print("\n" + "=" * 60)
    print(">>> RUNNING NLU (Qwen2.5-1.5B LoRA) INFERENCE TESTS <<<")
    print("=" * 60)

    base_name = "Qwen/Qwen2.5-1.5B-Instruct"
    model, tokenizer = load_model_and_tokenizer(base_name, adapter_path, use_4bit=use_4bit)

    system_prompt = (
        "Bạn là bộ phân tích NLU cho hệ thống đặt vé SmartEvent v1.2.\n"
        "Nhiệm vụ: Phân tích yêu cầu người dùng và trích xuất JSON duy nhất gồm:\n"
        "- primary_intent: Một trong 21 intent theo ontology (SEARCH_EVENT, TICKET_RECOMMEND, BOOKING_GUIDANCE, REFUND_POLICY, ...)\n"
        "- proposed_action: Hành động đề xuất chỉ đọc (SEARCH_EVENTS, GET_TICKET_OPTIONS, ...)\n"
        "- entities: dict chứa các thực thể đã bóc tách (city, quantity, budget_amount, budget_currency, ...)\n"
        "- state_delta: list các thao tác cập nhật trạng thái hội thoại [{\"operation\": \"SET\", \"slot\": \"...\", \"value\": ...}]\n"
        "Chỉ xuất duy nhất khối JSON, không giải thích thêm."
    )

    test_queries = [
        "Tìm cho tôi sự kiện âm nhạc tại Hà Nội cuối tuần này",
        "Tôi muốn mua 2 vé xem concert ở Sài Gòn, ngân sách dưới 1 triệu",
        "Sự kiện bị ban tổ chức hủy thì tôi có được hoàn tiền không?",
        "Giữ giúp tôi 2 vé VIP sự kiện Tech Summit nhé",
        "Hôm nay thời tiết đẹp quá nhỉ",
    ]

    for idx, query in enumerate(test_queries, 1):
        print(f"\n--- [NLU Test {idx}/{len(test_queries)}] ---")
        print(f"Query: \"{query}\"")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        t_start = time.time()
        with torch.no_grad():
            output_tokens = model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        elapsed = time.time() - t_start

        prompt_len = inputs["input_ids"].shape[1]
        gen_tokens = output_tokens[0][prompt_len:]
        response_text = tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

        tokens_sec = len(gen_tokens) / elapsed if elapsed > 0 else 0
        print(f"Latency: {elapsed:.2f}s ({len(gen_tokens)} tokens, {tokens_sec:.1f} tok/s)")
        print("Generated Output:")
        print(response_text)

    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"\n[CLEANUP] NLU model unloaded. Residual VRAM: {get_vram_mb():.1f}MB")


def run_rag_tests(adapter_path: Path, use_4bit: bool = True):
    print("\n" + "=" * 60)
    print(">>> RUNNING RAG (Qwen2.5-3B LoRA) INFERENCE TESTS <<<")
    print("=" * 60)

    base_name = "Qwen/Qwen2.5-3B-Instruct"
    model, tokenizer = load_model_and_tokenizer(base_name, adapter_path, use_4bit=use_4bit)

    policy_context = (
        "[Tài liệu chính sách SmartEvent v1.2 - Nguồn: FAQ & Chính sách hoàn vé đã duyệt]\n"
        "1. Điều kiện hoàn tiền: SmartEvent chỉ xử lý hoàn tiền 100% giá vé khi sự kiện bị hủy bỏ hoàn toàn bởi Ban tổ chức (BTC). "
        "Người mua cá nhân tự ý hủy vé hoặc không tham dự sự kiện sẽ KHÔNG được hoàn tiền.\n"
        "2. Thời hạn hoàn tiền: Thời gian xử lý hoàn tiền từ 7-14 ngày làm việc kể từ ngày BTC công bố hủy chính thức.\n"
        "3. Chuyển nhượng vé: Người dùng có thể chuyển nhượng vé cho người khác qua tính năng 'Chuyển vé' trên ứng dụng trước giờ mở cửa 24 tiếng.\n"
        "4. Nguyên tắc AI: Trợ lý AI chỉ giải đáp chính sách và hướng dẫn thao tác trên giao diện, TUYỆT ĐỐI không tự ý hủy đơn, hủy vé hoặc hoàn tiền thay người dùng."
    )

    system_prompt = (
        "Bạn là trợ lý SmartEvent. Nhiệm vụ của bạn là giải đáp thắc mắc người dùng dựa CHÍNH XÁC vào ngữ cảnh tài liệu chính sách được cung cấp bên dưới.\n"
        "Nếu ngữ cảnh không chứa thông tin, hãy thông báo rõ ràng là chính sách chưa quy định và đề xuất liên hệ hotline.\n"
        "Không bịa đặt thông tin. Tuân thủ tuyệt đối quy tắc chỉ đọc, không hứa hẹn giao dịch thay người dùng."
    )

    test_queries = [
        "Tôi bận việc đột xuất không đi xem ca nhạc được, tôi có được hoàn lại tiền vé không?",
        "Nếu ban tổ chức thông báo hủy show diễn, tôi được hoàn tiền thế nào và bao lâu nhận được?",
        "Bạn có thể bấm hủy vé giúp tôi ngay bây giờ không?",
        "Tôi muốn nhượng lại vé cho bạn tôi thì phải làm sao?",
    ]

    for idx, query in enumerate(test_queries, 1):
        print(f"\n--- [RAG Test {idx}/{len(test_queries)}] ---")
        print(f"Query: \"{query}\"")

        user_content = f"Ngữ cảnh tài liệu:\n{policy_context}\n\nCâu hỏi: {query}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        t_start = time.time()
        with torch.no_grad():
            output_tokens = model.generate(
                **inputs,
                max_new_tokens=350,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        elapsed = time.time() - t_start

        prompt_len = inputs["input_ids"].shape[1]
        gen_tokens = output_tokens[0][prompt_len:]
        response_text = tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

        tokens_sec = len(gen_tokens) / elapsed if elapsed > 0 else 0
        print(f"Latency: {elapsed:.2f}s ({len(gen_tokens)} tokens, {tokens_sec:.1f} tok/s)")
        print("Generated Output:")
        print(response_text)

    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"\n[CLEANUP] RAG model unloaded. Residual VRAM: {get_vram_mb():.1f}MB")


def main():
    parser = argparse.ArgumentParser(description="SmartEvent AI Model Inference Test")
    parser.add_argument("--mode", choices=["nlu", "rag", "all"], default="all")
    parser.add_argument("--no-4bit", action="store_true", help="Disable 4bit quantization")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    nlu_path = root / "models" / "unpacked_nlu_1.5b"
    rag_path = root / "models" / "unpacked_rag_3b"

    use_4bit = not args.no_4bit

    print(f"Device: {'CUDA (' + torch.cuda.get_device_name(0) + ')' if torch.cuda.is_available() else 'CPU'}")
    print(f"Quantization: {'4-bit NF4' if use_4bit else 'FP16/FP32'}")

    if args.mode in ("nlu", "all"):
        if not (nlu_path / "adapter_config.json").exists():
            print(f"Error: NLU adapter not found at {nlu_path}")
            sys.exit(1)
        run_nlu_tests(nlu_path, use_4bit=use_4bit)

    if args.mode in ("rag", "all"):
        if not (rag_path / "adapter_config.json").exists():
            print(f"Error: RAG adapter not found at {rag_path}")
            sys.exit(1)
        run_rag_tests(rag_path, use_4bit=use_4bit)

    print("\nAll model inference tests finished successfully.")


if __name__ == "__main__":
    main()
