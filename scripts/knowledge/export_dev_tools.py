"""Render requirements/dev.txt convenience list from the hashed dev.lock export."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = ROOT / "requirements/dev.lock"
DEFAULT_OUTPUT = ROOT / "requirements/dev.txt"
HEADER = "# Direct tool dependencies pinned. Runtime packages pinned in pyproject.toml."
DEV_GROUP_MARKER = "[dependency-groups]"


def direct_tool_names(pyproject: str) -> list[str]:
    lines = pyproject.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == DEV_GROUP_MARKER)
    names = []
    for line in lines[start + 1 :]:
        if line.startswith("["):
            break
        entry = line.strip().rstrip(",")
        if entry.startswith('"'):
            names.append(entry.strip('"').split("==")[0].split(";")[0].strip().lower())
    return names


def render(locked: str, pyproject: str) -> str:
    wanted = direct_tool_names(pyproject)
    versions: dict[str, str] = {}
    for line in locked.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", " ")):
            continue
        name, _, version = line.partition("==")
        version = version.split(";")[0].split()[0].strip()
        if name and name.lower() in wanted and name.lower() not in versions:
            versions[name.lower()] = f"{name}=={version}"
    missing = [name for name in wanted if name not in versions]
    if missing:
        raise ValueError(f"dev.lock missing direct tools: {missing}")
    return HEADER + "\n" + "\n".join(versions[name] for name in sorted(versions)) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
    parser.add_argument("--write", action="store_true", help="Regenerate dev.txt from dev.lock")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pyproject", type=Path, default=ROOT / "pyproject.toml")
    args = parser.parse_args(argv)
    rendered = render(
        args.lock.read_text(encoding="utf-8"), args.pyproject.read_text(encoding="utf-8")
    )
    if args.write:
        args.output.write_text(rendered, encoding="utf-8")
    if rendered != args.output.read_text(encoding="utf-8"):
        raise SystemExit(f"dev tools list drift: {args.output}")
    print(f"dev tools list verified: {args.output.name}")


if __name__ == "__main__":
    main()
