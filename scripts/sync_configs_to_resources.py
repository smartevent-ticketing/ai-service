"""One-way sync of reviewed configs/ into packaged resources/ fallback copies."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "configs"
DEFAULT_PACKAGE = ROOT / "src/smartevent_ai/resources"
TRACKED_SUFFIXES = (".yaml", ".json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_files(root: Path) -> set[Path]:
    return {
        p.relative_to(root) for p in root.rglob("*") if p.is_file() and p.suffix in TRACKED_SUFFIXES
    }


def find_drift(source: Path, package: Path) -> list[str]:
    expected, actual = tracked_files(source), tracked_files(package)
    drifts = []
    if expected != actual:
        drifts.append("Config/schema source and package file sets differ")
    for relative in sorted(expected | actual):
        origin, mirror = source / relative, package / relative
        if not origin.is_file() or not mirror.is_file():
            drifts.append(f"missing config pair: {origin} / {mirror}")
            continue
        if digest(origin) != digest(mirror):
            drifts.append(f"config drift: {relative.as_posix()}")
    return drifts


def write_package(source: Path, package: Path) -> list[str]:
    copied = []
    for relative in sorted(tracked_files(source)):
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or digest(target) != digest(source / relative):
            shutil.copyfile(source / relative, target)
            copied.append(relative.as_posix())
    stale = sorted(tracked_files(package) - tracked_files(source))
    for relative in stale:
        (package / relative).unlink()
        copied.append(f"removed {relative}")
    return copied


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    parser.add_argument("--write", action="store_true", help="Copy configs/ into resources/")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args(argv)
    if args.write:
        for name in write_package(args.source, args.package):
            print(name)
    drifts = find_drift(args.source, args.package)
    if drifts:
        raise SystemExit("\n".join(drifts))
    print("Runtime config source/package copies are byte-identical")


if __name__ == "__main__":
    main()
