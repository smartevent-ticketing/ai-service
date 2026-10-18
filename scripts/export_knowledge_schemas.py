"""Export/verify strict knowledge wire schemas and their packaged fallback copies."""

from __future__ import annotations

import argparse
from pathlib import Path

from smartevent_ai.adapters.outbound.knowledge.contracts import (
    CatalogRecord,
    ReleaseRecord,
    SourceRecord,
    canonical_json,
)
from smartevent_ai.infrastructure.knowledge_config import RagConfig
from smartevent_ai.tooling.knowledge.evaluate import EvaluationCase

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "rag_source.schema.json": SourceRecord,
    "rag_catalog.schema.json": CatalogRecord,
    "rag_release.schema.json": ReleaseRecord,
    "rag_config.schema.json": RagConfig,
    "rag_evaluation.schema.json": EvaluationCase,
}


def export(verify: bool = False) -> None:
    for name, model in SCHEMAS.items():
        data = canonical_json(
            {"$schema": "https://json-schema.org/draft/2020-12/schema", **model.model_json_schema()}
        )
        for directory in (ROOT / "configs/schemas", ROOT / "src/smartevent_ai/resources/schemas"):
            path = directory / name
            if verify:
                if not path.is_file() or path.read_bytes() != data:
                    raise SystemExit(f"Knowledge schema drift: {path}")
            else:
                directory.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
    print("Knowledge schemas verified" if verify else "Knowledge schemas exported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    export(parser.parse_args().verify)
