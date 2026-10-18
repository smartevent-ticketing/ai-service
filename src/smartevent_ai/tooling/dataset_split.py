"""Deterministic, group-disjoint dataset splitting with reproducibility hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ALGORITHM_VERSION = "sha256-linked-group-family-v3"
TRAIN_THRESHOLD = 0.77
VALIDATION_THRESHOLD = 0.885


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_samples(input_path: Path) -> tuple[list[dict[str, Any]], bytes]:
    raw = input_path.read_bytes()
    samples: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Dataset line {line_number} must be an object")
        samples.append(value)
    if not samples:
        raise ValueError("Dataset must contain at least one sample")
    return samples, raw


def split_dataset(
    input_path: Path,
    out_dir: Path,
    seed: str,
    schema_path: Path,
    *,
    source_revision: str | None = None,
) -> dict[str, object]:
    if not seed.strip():
        raise ValueError("seed must be non-empty")
    samples, raw_input = _load_samples(input_path)
    schema_bytes = schema_path.read_bytes()
    schema = json.loads(schema_bytes)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    sample_ids: set[object] = set()
    groups: set[str] = set()
    parents: dict[str, str] = {}

    def root(key: str) -> str:
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    for sample in samples:
        errors = list(validator.iter_errors(sample))
        if errors:
            raise ValueError(f"Invalid annotated sample: {errors[0].message}")
        metadata = sample.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Every sample must contain metadata")
        group = metadata.get("dialogue_group")
        if not isinstance(group, str) or not group.strip():
            raise ValueError("Every sample must contain a non-empty dialogue_group")
        groups.add(group)
        family = metadata.get("scenario_family")
        if not isinstance(family, str) or not family.strip():
            raise ValueError("Every sample must contain a non-empty scenario_family")
        # Connected components preserve BOTH constraints, including a dialogue
        # group spanning several families. Hashing pairs would leak either key.
        a, b = sorted((root("group:" + group), root("family:" + family)))
        parents[b] = a
        sample_id = sample.get("sample_id")
        if sample_id in sample_ids:
            raise ValueError("Duplicate sample_id detected")
        sample_ids.add(sample_id)

    buckets: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    group_assignment: dict[str, str] = {}
    components: dict[str, list[str]] = {}
    for key in sorted(parents):
        components.setdefault(root(key), []).append(key)
    for members in sorted(components.values()):
        key_bytes = json.dumps([seed, members], ensure_ascii=False, separators=(",", ":")).encode()
        digest = hashlib.sha256(key_bytes).digest()
        slot = int.from_bytes(digest[:8], "big") / 2**64
        bucket = (
            "train"
            if slot < TRAIN_THRESHOLD
            else "validation"
            if slot < VALIDATION_THRESHOLD
            else "test"
        )
        for member in members:
            if member.startswith("group:"):
                group_assignment[member.removeprefix("group:")] = bucket

    for sample in sorted(samples, key=lambda row: row["sample_id"]):
        group = str(sample["metadata"]["dialogue_group"])
        buckets[group_assignment[group]].append(sample)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_hashes: dict[str, str] = {}
    for name, rows in buckets.items():
        target = out_dir / f"{name}.jsonl"
        body = "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for item in rows
        )
        output_bytes = body.encode("utf-8")
        target.write_bytes(output_bytes)
        output_hashes[name] = _sha256_bytes(output_bytes)

    manifest: dict[str, object] = {
        "algorithm": ALGORITHM_VERSION,
        "seed": seed,
        "thresholds": {
            "train": TRAIN_THRESHOLD,
            "validation": VALIDATION_THRESHOLD - TRAIN_THRESHOLD,
            "test": 1 - VALIDATION_THRESHOLD,
        },
        "input_sha256": _sha256_bytes(raw_input),
        "schema_sha256": _sha256_bytes(schema_bytes),
        "sample_count": len(samples),
        "group_count": len(groups),
        "component_count": len(components),
        "split_unit": "connected_dialogue_groups_and_scenario_families",
        "evaluation_ready": all(buckets.values()),
        "warnings": [f"EMPTY_SPLIT:{name}" for name, rows in buckets.items() if not rows],
        "counts": {key: len(value) for key, value in buckets.items()},
        "group_counts": {
            key: sum(1 for bucket in group_assignment.values() if bucket == key) for key in buckets
        },
        "output_sha256": output_hashes,
    }
    if source_revision is not None:
        if not source_revision.strip():
            raise ValueError("source_revision must be non-empty when supplied")
        manifest["source_revision"] = source_revision

    (out_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    )
    return manifest
