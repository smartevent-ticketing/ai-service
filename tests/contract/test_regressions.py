"""Behavior regressions from the independent source audit (no live backend)."""

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import ROOT, SpyTransport
from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport
from smartevent_ai.domain.dialogue import (
    ClearGroup,
    DialoguePatch,
    DialogueState,
    Intent,
    Scope,
    Slot,
    merge_state,
)
from smartevent_ai.domain.errors import BackendUnavailable, ContractViolation
from smartevent_ai.domain.recommendation import TicketOption, recommend
from smartevent_ai.infrastructure.settings import Settings
from smartevent_ai.tooling.dataset_split import split_dataset

UID = "08c25afc-f9c9-4db0-aab7-02c779779d6c"


@pytest.mark.parametrize(
    "count,total,page,size", [(0, 1, 0, 10), (1, 2, 0, 10), (1, 11, 0, 10), (0, 11, 1, 10)]
)
def test_page_cardinality_must_match_totals(count: int, total: int, page: int, size: int) -> None:
    gateway = ReadOnlyToolGateway(
        ROOT / "configs/runtime_tool_registry.yaml",
        ROOT / "configs/implementation_gates.yaml",
        SpyTransport(),
    )
    pages = (total + size - 1) // size
    with pytest.raises(ContractViolation):
        gateway.project(
            gateway.tools["search_events"],
            {
                "content": [{}] * count,
                "totalElements": total,
                "page": page,
                "size": size,
                "totalPages": pages,
                "last": page == pages - 1,
            },
        )


@pytest.mark.asyncio
async def test_response_page_must_match_request(approved_registry: tuple[Path, Path]) -> None:
    spy = SpyTransport(
        {
            "success": True,
            "data": {
                "content": [],
                "page": 2,
                "size": 10,
                "totalElements": 0,
                "totalPages": 0,
                "last": True,
            },
        }
    )
    gateway = ReadOnlyToolGateway(*approved_registry, spy)
    with pytest.raises(ContractViolation, match="match request"):
        await gateway.execute("search_events", {"page": 0, "size": 10})


@pytest.mark.parametrize(
    "text,intent",
    [
        ("Thôi xem tổng tiền đơn hàng của tôi", Intent.ORDER_STATUS),
        ("Tổng thanh toán của tôi", Intent.PAYMENT_STATUS),
        ("Hoàn tiền tổng cộng bao nhiêu", Intent.REFUND_POLICY),
    ],
)
def test_task_switch_is_not_a_scope_answer(text: str, intent: Intent) -> None:
    state = DialogueState(quantity=3, budget_amount=800_000)
    parsed = RuleBasedVietnameseNLU().parse(text, state)
    assert parsed.intent is intent
    assert parsed.patch.budget_scope is None


def test_search_clarification_resumes_active_search() -> None:
    nlu = RuleBasedVietnameseNLU()
    first = nlu.parse("Tìm concert 3 vé dưới 800 nghìn", DialogueState())
    state = merge_state(DialogueState(), first.patch)
    second = nlu.parse("Tính tổng nhé", state)
    assert second.intent is Intent.SEARCH_EVENT
    assert merge_state(state, second.patch).search_query == state.search_query


@pytest.mark.parametrize("quantity", ["0", "21", "100", "-2", "1.5", "1,5", "9" * 1900])
def test_invalid_quantity_requires_clarification(quantity: str) -> None:
    state = DialogueState(quantity=3)
    parsed = RuleBasedVietnameseNLU().parse(f"Đổi thành {quantity} vé", state)
    assert parsed.needs_clarification
    assert merge_state(state, parsed.patch).quantity == 3


def test_clear_and_remove_preserve_domain_invariants() -> None:
    state = DialogueState(
        city="Hà Nội",
        search_query="concert",
        quantity=3,
        budget_amount=800_000,
        budget_scope=Scope.TOTAL,
    )
    cleared = merge_state(state, DialoguePatch(removed_slots=frozenset({Slot.BUDGET_AMOUNT})))
    assert cleared.budget_amount is None and cleared.budget_scope is Scope.UNKNOWN
    assert cleared.quantity == 3
    filters = merge_state(state, DialoguePatch(clear_group=ClearGroup.EVENT_FILTERS))
    assert filters.city is None and filters.search_query is None and filters.quantity == 3
    reset = merge_state(state, DialoguePatch(clear_group=ClearGroup.ALL_SLOTS, quantity=2))
    assert reset == DialogueState(quantity=2)


def test_http_user_can_remove_filter_and_reset() -> None:
    client = TestClient(create_app())
    old = {
        "city": "Hà Nội",
        "search_query": "concert",
        "quantity": 3,
        "budget_amount": 800_000,
        "budget_scope": "TOTAL",
    }
    result = client.post(
        "/api/v1/chat",
        json={
            "message": "Bỏ bộ lọc thành phố, tìm tất cả sự kiện",
            "previous_state": old,
        },
    ).json()
    assert result["state"]["city"] is None and result["state"]["search_query"] is None
    result = client.post(
        "/api/v1/chat",
        json={
            "message": "Bắt đầu lại",
            "previous_state": old,
        },
    ).json()
    assert result["state"]["quantity"] is None and result["state"]["budget_amount"] is None
    result = client.post(
        "/api/v1/chat",
        json={
            "message": "Bỏ ngân sách",
            "previous_state": old,
        },
    ).json()
    assert result["state"]["budget_amount"] is None
    assert result["state"]["budget_scope"] == "UNKNOWN"
    for value in (True, 1.5, "3"):
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "Xin chào",
                "previous_state": {"quantity": value},
            },
        )
        assert response.status_code == 422


def test_city_negation_and_budget_validation() -> None:
    nlu = RuleBasedVietnameseNLU()
    state = DialogueState(city="Hà Nội", budget_amount=800_000, budget_scope=Scope.TOTAL)
    parsed = nlu.parse("Không ở Hà Nội nữa, tìm sự kiện tại Đà Nẵng", state)
    assert merge_state(state, parsed.patch).city == "Đà Nẵng"
    parsed = nlu.parse("Bỏ thành phố Hà Nội", state)
    assert merge_state(state, parsed.patch).city is None
    for money in ("-1", "0.000000000000000000000000001"):
        parsed = nlu.parse(f"2 vé dưới {money} nghìn tổng", state)
        assert parsed.needs_clarification


@pytest.mark.parametrize("price", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_prices_rejected_at_domain_boundary(price: Decimal) -> None:
    with pytest.raises(ValueError):
        TicketOption("bad", price, 3, True, True)


def test_optimizer_rejects_invalid_counts_money_and_preserves_tie_break() -> None:
    base = TicketOption("b", Decimal(1), 3, True, True)
    for kwargs in ({"available": -1}, {"event_published": 1}, {"id": " "}):
        with pytest.raises(ValueError):
            replace(base, **kwargs)
    with pytest.raises(ValueError):
        recommend((base,), quantity=True, max_total=Decimal(1), complete_snapshot=True)
    with pytest.raises(ValueError):
        recommend((base,), quantity=1, max_total=Decimal("NaN"), complete_snapshot=True)
    result = recommend(
        (base, replace(base, id="a")), quantity=2, max_total=Decimal(2), complete_snapshot=True
    )
    assert [row.id for row in result.selected] == ["a", "b"]


def test_split_components_and_written_hashes(tmp_path: Path) -> None:
    template = json.loads(
        (ROOT / "datasets/examples/synthetic_vi.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    samples = []
    for i in range(100):
        row = json.loads(json.dumps(template))
        row["sample_id"] = f"SE-REG-{i:05d}"
        row["metadata"]["dialogue_group"] = f"g{i}"
        row["metadata"]["scenario_family"] = f"family{i // 2}"
        samples.append(row)
    # A dialogue connects two families: both must stay with the other group.
    samples[2]["metadata"]["dialogue_group"] = "g0"
    source = tmp_path / "source.jsonl"
    source.write_text("\n".join(json.dumps(x) for x in samples), encoding="utf-8")
    out = tmp_path / "out"
    manifest = split_dataset(
        source, out, "seed", ROOT / "docs/contexts/v1.2/schemas/training_sample.schema.json"
    )
    assert manifest["evaluation_ready"]
    seen: dict[str, str] = {}
    for name in ("train", "validation", "test"):
        raw = (out / f"{name}.jsonl").read_bytes()
        assert b"\r\n" not in raw
        assert hashlib.sha256(raw).hexdigest() == manifest["output_sha256"][name]
        for row in map(json.loads, raw.decode().splitlines()):
            for field in ("dialogue_group", "scenario_family"):
                key = field + ":" + row["metadata"][field]
                assert seen.setdefault(key, name) == name


@pytest.mark.parametrize(
    "route",
    [
        "/api/v1/payments/vnpay/ipn",
        "/api/v1/payments/vnpay/return",
        "/api/v1/tickets/refresh",
        "/api/v1/orders/cancel",
    ],
)
@pytest.mark.asyncio
async def test_side_effect_routes_denied_at_both_layers(route: str, tmp_path: Path) -> None:
    config = yaml.safe_load(
        (ROOT / "configs/runtime_tool_registry.yaml").read_text(encoding="utf-8")
    )
    config["tools"][0]["endpoint"] = route
    path = tmp_path / "unsafe.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())
    with pytest.raises(ContractViolation):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            route, query={}, max_bytes=262144, timeout_ms=1000
        )


@pytest.mark.parametrize(
    "body",
    [
        b'{"data":' + b"[" * 1000 + b"0" + b"]" * 1000 + b"}",
        b'{"data":NaN}',
        b'{"data":1e309}',
        b'{"data":Infinity}',
        b"{bad",
    ],
)
@pytest.mark.asyncio
async def test_malformed_backend_json_is_typed_error(
    body: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = httpx.AsyncClient

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    with pytest.raises(BackendUnavailable):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=262144, timeout_ms=1000
        )


@pytest.mark.asyncio
async def test_global_deadline_limits_trickling_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            for part in (b'{"success":', b"true,", b'"data":{}}'):
                await asyncio.sleep(0.06)
                yield part

    original = httpx.AsyncClient

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(
                200, stream=SlowStream(), headers={"content-type": "application/json"}
            )
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    with pytest.raises(BackendUnavailable):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=1000, timeout_ms=100
        )


@pytest.mark.asyncio
async def test_compressed_backend_is_denied_before_read(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnreadableStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError("Compressed bytes must not be decompressed")
            yield b""  # pragma: no cover

    original = httpx.AsyncClient

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["accept-encoding"] == "identity"
            return httpx.Response(
                200,
                stream=UnreadableStream(),
                headers={
                    "content-type": "application/json",
                    "content-encoding": "gzip",
                },
            )

        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    with pytest.raises(BackendUnavailable, match="Compressed"):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=1000, timeout_ms=100
        )


@pytest.mark.asyncio
async def test_json_text_braces_are_not_structural_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient
    data = {"success": True, "data": {"text": '{"untrusted":"quoted"}' * 100}}

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(lambda request: httpx.Response(200, json=data))
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    assert (
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=10000, timeout_ms=1000
        )
        == data
    )


def test_http_malformed_upstream_uses_safe_fallback(
    approved_registry: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, gates = approved_registry
    directory = registry.parent
    (directory / "runtime_tool_registry.yaml").write_bytes(registry.read_bytes())
    (directory / "implementation_gates.yaml").write_bytes(gates.read_bytes())
    original = httpx.AsyncClient

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b"[" * 1000, headers={"content-type": "application/json"}
            )
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    result = TestClient(create_app(Settings(config_dir=directory))).post(
        "/api/v1/chat", json={"message": "Tìm concert"}
    )
    assert result.status_code == 200
    assert result.json()["grounding"] == "NO_LIVE_DATA"
