"""Verify packaged fallback configs exactly match the reviewed root configs."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    mismatches: list[str] = []
    source_root, package_root = ROOT / "configs", ROOT / "src/smartevent_ai/resources"
    expected = {
        p.relative_to(source_root) for p in source_root.rglob("*") if p.suffix in (".yaml", ".json")
    }
    actual = {
        p.relative_to(package_root)
        for p in package_root.rglob("*")
        if p.suffix in (".yaml", ".json")
    }
    if expected != actual:
        mismatches.append("Config/schema source and package file sets differ")
    for relative in sorted(expected | actual):
        source, packaged = source_root / relative, package_root / relative
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
