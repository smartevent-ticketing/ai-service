"""Check generated hash exports against the frozen universal lock without network."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    environment = dict(os.environ, UV_CACHE_DIR=str(ROOT / ".venv/uv-cache"))
    subprocess.run(  # noqa: S603 -- fixed module and local lock, no shell
        [sys.executable, "-m", "uv", "lock", "--check", "--offline"],
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=60,
    )
    for filename, flags in (
        ("runtime.lock", ["--no-dev"]),
        ("dev.lock", []),
        ("rag.lock", ["--no-dev", "--extra", "rag-ingest", "--extra", "rag-semantic"]),
    ):
        result = subprocess.run(  # noqa: S603 -- fixed module and export options
            [
                sys.executable,
                "-m",
                "uv",
                "export",
                "--quiet",
                "--frozen",
                "--no-header",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                *flags,
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        if (ROOT / "requirements" / filename).read_bytes() != result.stdout.encode("utf-8"):
            raise SystemExit(f"Dependency export drift: {filename}")
    print("Frozen dependency lock and hashed exports verified")


if __name__ == "__main__":
    main()
