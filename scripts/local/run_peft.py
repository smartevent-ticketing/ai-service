"""Run the existing NLU adapter offline without changing deployed defaults."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE_ID = "Qwen/Qwen2.5-1.5B-Instruct"


def verify_api(port: int, message: str) -> None:
    """Probe the running process, without allocating a second GPU model."""
    import httpx

    origin = f"http://127.0.0.1:{port}"
    with httpx.Client(base_url=origin, trust_env=False, follow_redirects=False) as client:
        response = client.get("/health/ready", timeout=5)
        response.raise_for_status()
        ready = response.json()
    if (
        ready.get("model_backend") != "peft"
        or ready.get("nlu_startup") != "ready"
        or ready.get("business_tools_enabled") != ["search_events"]
        or ready.get("business_tool_capabilities", {})
        .get("search_events", {})
        .get("date_price_filters")
        is not True
    ):
        raise ValueError("API has not completed PEFT warmup and verified search deployment")
    with httpx.Client(base_url=origin, trust_env=False, follow_redirects=False) as client:
        response = client.post("/api/v1/chat", json={"message": message}, timeout=25)
        response.raise_for_status()
        result = response.json()
    if (
        result.get("mode") != "model"
        or result.get("intent") != "SEARCH_EVENT"
        or result.get("tool_called") != "search_events"
        or result.get("grounding") != "BACKEND_READ"
        or result.get("status") not in ("OK", "EMPTY")
    ):
        raise ValueError("Chat did not complete model -> public backend search")
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "tool_called": result["tool_called"],
                "grounding": result["grounding"],
                "status": result["status"],
                "event_count": len(result.get("events", [])),
            }
        )
    )
    print("MODEL_BACKEND_HTTP_OK (one search case; not a model quality benchmark)")


def configure(
    base_override: str | None,
    search_config_dir: str | None = None,
    backend_url: str = "http://127.0.0.1:8080",
) -> tuple[Path, Path]:
    adapter = ROOT / "models/unpacked_nlu_1.5b"
    for name in ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json"):
        if not (adapter / name).is_file():
            raise ValueError(f"Missing adapter file: {adapter / name}")
    config = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
    if config.get("base_model_name_or_path") != BASE_ID:
        raise ValueError("Adapter does not declare the expected Qwen2.5-1.5B base")
    if base_override:
        base = Path(base_override).expanduser().resolve()
    else:
        hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
        hub = Path(os.environ.get("HF_HUB_CACHE", str(hf_home / "hub")))
        cached = hub / "models--Qwen--Qwen2.5-1.5B-Instruct"
        ref = cached / "refs/main"
        if not ref.is_file():
            raise ValueError("Base not cached; pass --base-model-path with local full weights")
        revision = ref.read_text(encoding="utf-8").strip()
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("Invalid cached base revision")
        base = cached / "snapshots" / revision
    if not (base / "config.json").is_file() or not (base / "model.safetensors").is_file():
        raise ValueError(f"Incomplete local base model: {base}")
    base_config = json.loads((base / "config.json").read_text(encoding="utf-8"))
    if base_config.get("model_type") != "qwen2" or base_config.get("hidden_size") != 1536:
        raise ValueError("Local base configuration does not match the NLU adapter")
    sys.path.insert(0, str(ROOT / "src"))
    config_dir = ROOT / "configs"
    if search_config_dir:
        sys.path.insert(0, str(ROOT / "scripts"))
        from public_search_deployment import validate_deployment

        config_dir = Path(search_config_dir).expanduser().resolve()
        validate_deployment(config_dir)
    from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport

    SafeBackendTransport(backend_url)  # Validate the fixed origin before loading GPU weights.
    # These settings exist only in this child process. Gates stay in repo configs.
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        HF_HUB_DISABLE_PROGRESS_BARS="1",
        NLU_BACKEND="peft",
        NLU_ADAPTER_PATH=str(adapter),
        NLU_BASE_MODEL=str(base),
        NLU_LOAD_4BIT="true",
        NLU_PRELOAD="true",
        RAG_BACKEND="extractive",
        POLICY_BACKEND="artifact",
        CONFIG_DIR=str(config_dir),
        BACKEND_BASE_URL=backend_url,
    )
    return adapter, base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "smoke", "serve", "verify"), default="serve")
    parser.add_argument("--base-model-path")
    parser.add_argument(
        "--search-config-dir", help="Verified search profile produced by verify-public-search.ps1"
    )
    parser.add_argument("--backend", default="http://127.0.0.1:8080")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--message", default="Tìm giúp tôi 2 vé ở Hà Nội.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    if args.mode == "verify":
        verify_api(args.port, args.message)
        return 0
    adapter, base = configure(args.base_model_path, args.search_config_dir, args.backend)
    print(f"NLU: PEFT NF4; adapter={adapter}; base={base}", flush=True)
    print(f"RAG: extractive; config={os.environ['CONFIG_DIR']}", flush=True)
    print(
        f"Backend: {args.backend}; search={'verified profile' if args.search_config_dir else 'disabled'}",
        flush=True,
    )
    if args.mode == "check":
        print("FILES_OK (does not load model or start HTTP)")
        return 0

    import torch

    if not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; this local NF4 profile requires the NVIDIA GPU")
    if args.mode == "smoke":
        from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
        from smartevent_ai.domain.dialogue import DialogueState, Intent

        provider = PeftTransformerNLU(adapter_path=adapter, base_model_name=str(base))
        result = provider.parse(args.message, DialogueState())
        print(json.dumps(asdict(result), ensure_ascii=False, default=str), flush=True)
        if result.mode != "model":
            print("MODEL_SMOKE_FAILED: fallback is not a successful model inference")
            return 1
        if args.message == parser.get_default("message") and (
            result.intent != Intent.SEARCH_EVENT
            or result.patch is None
            or result.patch.city != "Hà Nội"
            or result.patch.quantity != 2
        ):
            print("MODEL_SMOKE_FAILED: unexpected result for the built-in search case")
            return 1
        print("MODEL_SMOKE_OK (one case; not a quality benchmark or E2E approval)")
        return 0

    import uvicorn

    if args.search_config_dir:
        import asyncio
        from smartevent_ai.infrastructure.bootstrap import build_chat
        from smartevent_ai.infrastructure.settings import Settings

        _, gateway = build_chat(Settings())
        asyncio.run(gateway.execute("search_events", {"page": 0, "size": 1}))
        print("BACKEND_SEARCH_PREFLIGHT_OK (GET only)", flush=True)
    print(f"Chat API: http://127.0.0.1:{args.port}/docs", flush=True)
    uvicorn.run("smartevent_ai.main:app", host="127.0.0.1", port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
