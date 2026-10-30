"""Exact search labels on development seeds; not held-out model acceptance."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.domain.dialogue import DialogueState, merge_state
from smartevent_ai.domain.search import EventSearchCriteria

CASES = [
    json.loads(line)
    for line in (Path(__file__).resolve().parents[2] / "datasets/evaluation/chatbot_v2_seed.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
][:30]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_search_seed_has_exact_tool_arguments(case):
    now = datetime.fromisoformat(case["reference_time"])
    understood = RuleBasedVietnameseNLU(lambda: now).parse(case["message"], DialogueState())
    state = merge_state(DialogueState(), understood.patch)
    assert understood.intent.value == case["expected"]["intent"]
    assert state.city == case["expected"]["city"]
    if case["expected"]["status"] == "CLARIFY":
        assert understood.needs_clarification and case["expected"]["tool_arguments"] is None
    else:
        assert not understood.needs_clarification
        assert (
            EventSearchCriteria.from_state(state).as_tool_arguments()
            == case["expected"]["tool_arguments"]
        )
