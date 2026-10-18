import json
from pathlib import Path

import pytest

from smartevent_ai.tooling.dataset_split import split_dataset

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/contexts/v1.2/schemas/training_sample.schema.json"


def _rows() -> list[dict[str, object]]:
    return [
        {
            "sample_id": f"SE-TEST-{i:05d}",
            "dataset_contract": "1.2",
            "dataset_version": "test-1",
            "language": "vi",
            "task": "intent_slot",
            "previous_state": {},
            "user_message": "Tìm sự kiện",
            "expected": {
                "primary_intent": "SEARCH_EVENT",
                "state_delta": [],
                "proposed_action": "SEARCH_EVENTS",
            },
            "metadata": {
                "source": "synthetic_reviewed",
                "scenario": "find-event",
                "dialogue_group": f"g{i // 3}",
                "scenario_family": "search",
            },
        }
        for i in range(300)
    ]


def test_dataset_split_deterministic_disjoint_groups_and_hashes(tmp_path: Path) -> None:
    data = tmp_path / "raw.jsonl"
    data.write_text("\n".join(json.dumps(x) for x in _rows()), encoding="utf-8")
    m1 = split_dataset(data, tmp_path / "a", "seed", SCHEMA, source_revision="abc123")
    m2 = split_dataset(data, tmp_path / "b", "seed", SCHEMA, source_revision="abc123")
    assert m1 == m2
    assert m1["input_sha256"] and m1["schema_sha256"]
    assert m1["source_revision"] == "abc123"
    groups: list[set[str]] = []
    for filename in ("train", "validation", "test"):
        rows = [
            json.loads(x) for x in (tmp_path / "a" / f"{filename}.jsonl").read_text().splitlines()
        ]
        groups.append({x["metadata"]["dialogue_group"] for x in rows})
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])


def test_dataset_rejects_missing_group(tmp_path: Path) -> None:
    file = tmp_path / "bad.jsonl"
    file.write_text('{"sample_id":"1","metadata":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        split_dataset(file, tmp_path / "out", "s", SCHEMA)


def test_dataset_rejects_empty_seed_and_empty_input(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        split_dataset(empty, tmp_path / "out", "seed", SCHEMA)
    valid = tmp_path / "valid.jsonl"
    valid.write_text(json.dumps(_rows()[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        split_dataset(valid, tmp_path / "out2", " ", SCHEMA)
