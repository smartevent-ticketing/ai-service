"""Generate/verify deterministic SHA-256 manifest for distributable source files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST_SHA256.json"
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "htmlcov",
}
EXCLUDED_FILE_NAMES = {".coverage", "MANIFEST_SHA256.json"}
SOURCE_DIRECTORIES = {
    "src",
    "scripts",
    "tests",
    "configs",
    "datasets",
    "docs",
    "requirements",
    ".github",
}
SOURCE_FILES = {
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
    "Dockerfile",
    "Makefile",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".python-version",
    ".env.example",
}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if len(relative.parts) == 1:
        if path.name not in SOURCE_FILES:
            return False
    elif relative.parts[0] not in SOURCE_DIRECTORIES:
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.suffix == ".log":
        return False
    if path.name in EXCLUDED_FILE_NAMES or path.suffix == ".pyc":
        return False
    if any(part in EXCLUDED_DIR_NAMES or part.endswith(".egg-info") for part in relative.parts):
        return False
    return path.is_file()


def build_manifest() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        if not should_include(path):
            continue
        relative = path.relative_to(ROOT).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def write_manifest() -> None:
    MANIFEST.write_bytes((json.dumps(build_manifest(), indent=2, sort_keys=True) + "\n").encode())
    print(f"Wrote {MANIFEST.name}")


def verify_manifest() -> None:
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = build_manifest()
    if expected != actual:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(key for key in set(expected) & set(actual) if expected[key] != actual[key])
        raise SystemExit(
            "Source manifest mismatch\n"
            f"missing={missing[:10]}\nextra={extra[:10]}\nchanged={changed[:10]}"
        )
    print(f"Source manifest verified: {len(actual)} files")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify_manifest() if args.verify else write_manifest()


if __name__ == "__main__":
    main()
