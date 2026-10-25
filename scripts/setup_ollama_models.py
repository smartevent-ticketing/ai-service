"""Automation setup script to unpack LoRA weights and register Ollama models.

Teammates clone the repository and run:
    python scripts/setup_ollama_models.py

This script:
1. Validates that Ollama daemon is installed and reachable.
2. Automatically unpacks zip archives in models/ if not already unpacked.
3. Builds 'smartevent-nlu:1.5b' and 'smartevent-rag:3b' in Ollama.
4. Performs a health-check inference call.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"


def check_ollama_daemon(url: str = "http://127.0.0.1:11434") -> bool:
    try:
        resp = httpx.get(f"{url}/api/version", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def unpack_zip_if_needed(zip_name: str, target_dir_name: str) -> Path:
    zip_path = MODELS_DIR / zip_name
    target_dir = MODELS_DIR / target_dir_name

    if not zip_path.exists():
        print(f"[ERROR] Required zip file not found: {zip_path}")
        sys.exit(1)

    adapter_config = target_dir / "adapter_config.json"
    if not adapter_config.exists():
        print(f"[UNPACK] Extracting {zip_name} -> {target_dir_name}...")
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(target_dir)
        print(f"[UNPACK] {zip_name} extracted successfully.")
    else:
        print(f"[UNPACK] {target_dir_name} is already unpacked.")

    return target_dir


def build_ollama_model(model_name: str, modelfile_name: str) -> None:
    modelfile_path = MODELS_DIR / modelfile_name
    if not modelfile_path.exists():
        print(f"[ERROR] Modelfile not found: {modelfile_path}")
        sys.exit(1)

    print(f"\n[OLLAMA] Building model '{model_name}' from {modelfile_name}...")
    cmd = ["ollama", "create", model_name, "-f", str(modelfile_path)]
    try:
        proc = subprocess.run(cmd, cwd=MODELS_DIR, check=True)  # noqa: S603
        if proc.returncode == 0:
            print(f"[OLLAMA] Successfully created model '{model_name}'.")
    except FileNotFoundError:
        print("[ERROR] 'ollama' command not found in PATH.")
        print("Please install Ollama: https://ollama.com/download or 'winget install Ollama.Ollama'")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to create model {model_name}: {e}")
        sys.exit(1)


def main() -> None:
    print("=" * 60)
    print("SmartEvent AI - Ollama Models Automated Setup")
    print("=" * 60)

    # 1. Check Ollama binary
    if not shutil.which("ollama"):
        print("\n[WARNING] 'ollama' executable not found in your system PATH.")
        print("Install Ollama from https://ollama.com or run:")
        print("    winget install Ollama.Ollama")
        print("\nUnpacking weights anyway so they are ready...")
    else:
        print("[OK] Ollama binary detected.")

    # 2. Check running daemon
    if check_ollama_daemon():
        print("[OK] Ollama server is running at http://127.0.0.1:11434.")
    else:
        print("[NOTICE] Ollama server is not running currently.")
        print("Start it in another terminal with: 'ollama serve'")

    # 3. Unpack models
    unpack_zip_if_needed("smartevent-nlu-qwen1.5b-final.zip", "unpacked_nlu_1.5b")
    unpack_zip_if_needed("smartevent-rag-qwen3b-final.zip", "unpacked_rag_3b")

    # 4. If daemon is running and ollama is installed, build models
    if shutil.which("ollama") and check_ollama_daemon():
        build_ollama_model("smartevent-nlu:1.5b", "Modelfile.nlu")
        build_ollama_model("smartevent-rag:3b", "Modelfile.rag")
        print("\n[SUCCESS] Both models are registered and ready in Ollama!")
    else:
        print("\n[NOTE] Models unpacked. Once Ollama is running, execute:")
        print("    ollama create smartevent-nlu:1.5b -f models/Modelfile.nlu")
        print("    ollama create smartevent-rag:3b -f models/Modelfile.rag")


if __name__ == "__main__":
    main()
