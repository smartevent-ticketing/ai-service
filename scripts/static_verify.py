"""Dependency-direction and read-only static guard with no external tooling."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/smartevent_ai"
errors: list[str] = []

INNER_FORBIDDEN_PREFIXES = (
    "fastapi",
    "httpx",
    "pydantic",
    "pydantic_settings",
    "yaml",
    "jsonschema",
    "sqlalchemy",
    "psycopg",
    "redis",
    "langchain",
    "tokenizers",
    "transformers",
    "sentence_transformers",
    "onnxruntime",
    "numpy",
)


def imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


for file in SOURCE.rglob("*.py"):
    tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    rel = file.relative_to(ROOT).as_posix()
    modules = imported_modules(tree)
    if "/tooling/" not in rel and any(m.startswith("smartevent_ai.tooling") for m in modules):
        errors.append(f"Runtime layer imports offline tooling/writers: {rel}")

    if "/domain/" in rel:
        for module in modules:
            if module.split(".")[0] not in sys.stdlib_module_names and not module.startswith(
                "smartevent_ai.domain"
            ):
                errors.append(f"Domain must be standard-library-only: {rel}: {module}")
            if (
                module.startswith("smartevent_ai.application")
                or module.startswith("smartevent_ai.adapters")
                or module.startswith("smartevent_ai.infrastructure")
            ):
                errors.append(f"Domain dependency inversion violation: {rel}: {module}")
            if module.startswith(INNER_FORBIDDEN_PREFIXES):
                errors.append(f"Domain must stay framework/library independent: {rel}: {module}")

    if "/application/" in rel:
        for module in modules:
            if module.startswith("smartevent_ai.adapters") or module.startswith(
                "smartevent_ai.infrastructure"
            ):
                errors.append(f"Application depends on outer layer: {rel}: {module}")
            if module.startswith(INNER_FORBIDDEN_PREFIXES):
                errors.append(
                    f"Application imports outer validation/transport library: {rel}: {module}"
                )

    if "/outbound/" in rel:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr.lower() in ("post", "put", "patch", "delete"):
                    errors.append(f"Outbound adapter may not call mutation method: {rel}")

if errors:
    raise SystemExit("\n".join(sorted(set(errors))))
print("Clean Architecture dependency and read-only outbound static guard OK")
