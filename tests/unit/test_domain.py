from decimal import Decimal

import pytest

from smartevent_ai.domain.dialogue import DialoguePatch, DialogueState, Scope, merge_state
from smartevent_ai.domain.recommendation import TicketOption, recommend
from smartevent_ai.domain.search import EventSearchCriteria


def test_state_change_is_pure() -> None:
    first = DialogueState(quantity=2, budget_amount=1_200_000, budget_scope=Scope.TOTAL)
    nxt = merge_state(first, DialoguePatch(quantity=3))
    assert first.quantity == 2
    assert nxt.quantity == 3 and nxt.budget_amount == 1_200_000


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DialogueState(quantity=0),
        lambda: DialogueState(quantity=21),
        lambda: DialogueState(budget_scope=Scope.TOTAL),
        lambda: DialogueState(city=""),
        lambda: DialogueState(search_query="x" * 121),
    ],
)
def test_state_rejects_invalid(factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        factory()


def test_search_criteria_uses_structured_state() -> None:
    state = DialogueState(city="Hà Nội", search_query="concert")
    criteria = EventSearchCriteria.from_state(state)
    assert criteria.as_tool_arguments() == {
        "q": "concert",
        "city": "Hà Nội",
        "page": 0,
        "size": 10,
    }


def test_recommend_ignores_violating_options() -> None:
    options = (
        TicketOption("a", Decimal("100000"), 3, True, True),
        TicketOption("b", Decimal("50000"), 1, True, True),
        TicketOption("c", Decimal("20000"), 9, False, True),
    )
    result = recommend(options, quantity=2, max_total=Decimal("250000"), complete_snapshot=True)
    assert [x.id for x in result.selected] == ["a"]


def test_incomplete_snapshot_fails_closed() -> None:
    result = recommend(
        (TicketOption("a", Decimal(1), 3, True, True),),
        quantity=1,
        max_total=Decimal(100),
        complete_snapshot=False,
    )
    assert not result.selected and result.reason == "INCOMPLETE_SNAPSHOT"


def test_search_criteria_validation_and_category_id() -> None:
    from uuid import UUID

    category = UUID("08c25afc-f9c9-4db0-aab7-02c779779d6c")
    criteria = EventSearchCriteria(category_id=category, page=9, size=20)
    assert criteria.as_tool_arguments()["categoryId"] == str(category)
    for kwargs in (
        {"query": ""},
        {"city": ""},
        {"page": 10},
        {"size": 0},
    ):
        with pytest.raises(ValueError):
            EventSearchCriteria(**kwargs)


def test_recommend_rejects_invalid_criteria() -> None:
    with pytest.raises(ValueError):
        recommend((), quantity=0, max_total=Decimal("1"), complete_snapshot=True)
