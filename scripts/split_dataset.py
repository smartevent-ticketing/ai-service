"""CLI wrapper for the packaged deterministic dataset splitter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from smartevent_ai.tooling.dataset_split import split_dataset

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "docs/contexts/v1.2/schemas/training_sample.schema.json"


def split(input_path: Path, out_dir: Path, seed: str) -> dict[str, object]:
    """Backward-compatible helper used by existing automation."""
    return split_dataset(input_path, out_dir, seed, DEFAULT_SCHEMA)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--seed", default="smartevent-v1")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    manifest = split_dataset(
        args.input,
        args.out,
        args.seed,
        args.schema,
        source_revision=args.source_revision,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
