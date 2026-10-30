"""Local demo: evict old GPU weights before loading the next PEFT adapter/base."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from run_peft import ROOT, configure

RAG_BASE = "Qwen/Qwen2.5-3B-Instruct"
DEFAULT_HELP = ROOT / "artifacts/local-sequential-help"
CURRENT_PROFILE = ROOT / "artifacts/local-sequential-help-current.json"


def serving_config(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if CURRENT_PROFILE.is_file():
        saved = json.loads(CURRENT_PROFILE.read_text("utf-8"))
        if saved.get("version") != 1 or not isinstance(saved.get("config_dir"), str):
            raise ValueError("Invalid local demo profile reference; run -Mode prepare again")
        return Path(saved["config_dir"]).resolve()
    return DEFAULT_HELP / "configs"


def prepare_help(output: Path) -> Path:
    from datetime import UTC, datetime
    from tempfile import NamedTemporaryFile
    from build_local_help import build

    output = output.expanduser().resolve()
    if output.exists():
        output = output.with_name(output.name + datetime.now(UTC).strftime("-%Y%m%dT%H%M%S%f"))
        print(f"Preserving prior output; using new directory: {output}", flush=True)
    build(output)
    config = output / "configs"
    validate_demo_config(config)
    # Publish the reference only after all existing corpus/HTTP checks passed.
    # Failed builds leave both prior artifacts and the last good reference intact.
    CURRENT_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=CURRENT_PROFILE.parent, delete=False
    ) as stream:
        json.dump({"version": 1, "config_dir": str(config)}, stream)
        temporary = Path(stream.name)
    os.replace(temporary, CURRENT_PROFILE)
    print(f"Demo profile selected: {config}", flush=True)
    return config


def validate_demo_config(directory: Path) -> None:
    """Refuse half-built or stale corpus configurations."""
    from datetime import UTC, datetime
    from hashlib import sha256
    from build_local_help import CASES
    from public_search_deployment import source_fingerprint, validate_report

    report = json.loads((directory / "help_evidence.json").read_text("utf-8"))
    if (
        report.get("scope") != "local-demo-help-only"
        or report.get("source_sha256") != source_fingerprint()
        or report.get("approval_sha256")
        != sha256((ROOT / "datasets/help_review_2026_10_30/approval.json").read_bytes()).hexdigest()
        or datetime.fromisoformat(report["expires_at"]) <= datetime.now(UTC)
        or len(report.get("cases", [])) != len(CASES)
        or any(c.get("passed") is not True for c in report["cases"])
        or any(
            report.get(key) is not True
            for key in (
                "no_match",
                "revocation",
                "blocked_gate",
                "tampered_release",
                "expired_catalog",
                "http_routing",
                "private_queries_not_retrieved",
                "corpus_readonly",
            )
        )
    ):
        raise ValueError("Missing, stale or failed local corpus evidence; run -Mode prepare again")
    import yaml

    registry = yaml.safe_load((directory / "runtime_tool_registry.yaml").read_text("utf-8"))
    enabled = [t["name"] for t in registry["tools"] if t["enabled"]]
    if enabled:
        if enabled != ["search_events"]:
            raise ValueError("Demo permits only independently verified public search")
        validate_report(directory / "public_search_evidence.json")


def rag_paths(override: str | None) -> tuple[Path, Path]:
    adapter = ROOT / "models/unpacked_rag_3b"
    for name in ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json"):
        if not (adapter / name).is_file():
            raise ValueError(f"Missing RAG file: {adapter / name}")
    if (
        json.loads((adapter / "adapter_config.json").read_text("utf-8")).get(
            "base_model_name_or_path"
        )
        != RAG_BASE
    ):
        raise ValueError("RAG adapter does not match Qwen2.5-3B-Instruct")
    if override:
        base = Path(override).expanduser().resolve()
    else:
        hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
        hub = Path(os.environ.get("HF_HUB_CACHE", str(hf_home / "hub")))
        cached = hub / "models--Qwen--Qwen2.5-3B-Instruct"
        revision = (cached / "refs/main").read_text("utf-8").strip()
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("Invalid cached RAG revision")
        base = cached / "snapshots" / revision
    config = json.loads((base / "config.json").read_text("utf-8"))
    if config.get("model_type") != "qwen2" or config.get("hidden_size") != 2048:
        raise ValueError("Local base does not match RAG adapter")
    if not (base / "model.safetensors").is_file():
        index = json.loads((base / "model.safetensors.index.json").read_text("utf-8"))
        for shard in set(index["weight_map"].values()):
            if Path(shard).name != shard or not (base / shard).is_file():
                raise ValueError("Incomplete RAG base weights")
    return adapter, base


def smoke(report_path: Path) -> int:
    from smartevent_ai.infrastructure.bootstrap import build_chat
    from smartevent_ai.infrastructure.settings import Settings

    # This checks model execution directly with DEMO_INPUT; no corpus gate is bypassed.
    chat, _ = build_chat(Settings())
    synth = chat._policies._synthesizer
    records = []
    try:
        for role in ("nlu", "rag", "nlu"):
            started = time.perf_counter()
            if role == "nlu":
                chat.warmup_nlu()
                mode = chat.last_nlu_mode
            else:
                context = "DEMO_INPUT: SmartEvent hỗ trợ thanh toán qua VNPay. Nguồn: DEMO-01."
                answer = synth.synthesize("Có phương thức thanh toán nào?", context)
                mode = synth.last_mode
                print(json.dumps({"demo_rag_output": answer}, ensure_ascii=False), flush=True)
            import torch

            state = chat.model_runtime_status()
            record = {
                "role": role,
                "mode": mode,
                "seconds": round(time.perf_counter() - started, 3),
                "allocated_mib": round(torch.cuda.memory_allocated() / 2**20),
                "reserved_mib": round(torch.cuda.memory_reserved() / 2**20),
                "runtime": state,
            }
            records.append(record)
            print(json.dumps(record), flush=True)
            if mode != "model" or state["active_model"] != role:
                raise ValueError("Sequential smoke reached fallback; this is not model success")
            # Verify the inactive provider has no model/tokenizer references.
            inactive = synth if role == "nlu" else chat._nlu
            if inactive._model is not None or inactive._tokenizer is not None:
                raise ValueError("Inactive provider retained weights")
        print("SEQUENTIAL_MODEL_SMOKE_OK (NLU -> RAG -> NLU; not corpus/E2E/quality approval)")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"scope": "model-switch-only", "steps": records}, indent=2), encoding="utf-8"
        )
        print(f"Timing report: {report_path}")
        return 0
    finally:
        chat.close_models()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "prepare", "smoke", "serve"), default="serve")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--help-output", type=Path, default=DEFAULT_HELP)
    parser.add_argument("--base-model-path")
    parser.add_argument("--rag-base-model-path")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    configure(args.base_model_path)
    adapter, base = rag_paths(args.rag_base_model_path)
    os.environ.update(
        PEFT_SEQUENTIAL="true",
        RAG_BACKEND="peft",
        RAG_LOAD_4BIT="true",
        RAG_ADAPTER_PATH=str(adapter),
        RAG_BASE_MODEL=str(base),
        NLU_TIMEOUT_SECONDS="180",
        RAG_GENERATION_TIMEOUT_SECONDS="180",
    )
    sys.path.insert(0, str(ROOT / "scripts"))
    if args.mode == "prepare":
        os.environ.update(
            NLU_BACKEND="rule",
            RAG_BACKEND="extractive",
            PEFT_SEQUENTIAL="false",
            NLU_PRELOAD="false",
        )
        prepare_help(args.help_output)
        return 0
    print(
        "Sequential PEFT NF4: one model on GPU; old weights evicted, no CPU model cache.",
        flush=True,
    )
    print(f"RAG adapter={adapter}; base={base}", flush=True)
    if args.mode == "check":
        print("FILES_OK (does not load model or approve any corpus)")
        return 0

    import torch

    if not torch.cuda.is_available():
        raise ValueError("CUDA is required for this sequential NF4 demo")
    free, _ = torch.cuda.mem_get_info()
    if free < 2700 * 2**20:
        raise ValueError(
            "Less than 2700 MiB free VRAM. Stop the old model API before starting this demo."
        )
    if args.mode == "smoke":
        from datetime import datetime, UTC

        report = (
            args.report
            or ROOT / "artifacts" / f"sequential-smoke-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
        )
        if report.exists():
            raise ValueError("Smoke report must be new; preserve prior evidence")
        return smoke(report)
    from smartevent_ai.infrastructure.bootstrap import build_chat
    from smartevent_ai.infrastructure.settings import Settings

    config_dir = serving_config(args.config_dir)
    os.environ["CONFIG_DIR"] = str(config_dir)
    validate_demo_config(config_dir)
    chat, _ = build_chat(Settings())
    if chat.policy_status() != "ready":
        raise ValueError(
            "Approved corpus is not ready. Run -Mode prepare first or supply -ConfigDir."
        )
    chat.close_models()
    print(f"API: http://127.0.0.1:{args.port}/docs; timeout: 180s per model stage.", flush=True)
    print("RAG output remains evidence-checked and can return extractive_fallback.", flush=True)
    import uvicorn

    uvicorn.run("smartevent_ai.main:app", host="127.0.0.1", port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
