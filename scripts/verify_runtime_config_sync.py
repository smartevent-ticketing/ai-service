"""Verify packaged fallback configs exactly match the reviewed root configs."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    (
        ROOT / "configs/runtime_tool_registry.yaml",
        ROOT / "src/smartevent_ai/resources/runtime_tool_registry.yaml",
    ),
    (
        ROOT / "configs/implementation_gates.yaml",
        ROOT / "src/smartevent_ai/resources/implementation_gates.yaml",
    ),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    mismatches: list[str] = []
    for source, packaged in PAIRS:
        if not source.is_file() or not packaged.is_file():
            mismatches.append(f"missing config pair: {source} / {packaged}")
            continue
        if digest(source) != digest(packaged):
            mismatches.append(f"config drift: {source.name}")
    if mismatches:
        raise SystemExit("\n".join(mismatches))
    print("Runtime config source/package copies are byte-identical")


if __name__ == "__main__":
    main()
