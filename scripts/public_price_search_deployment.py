"""Verify scoped public price search and parent visibility on a disposable backend."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import yaml

import public_search_deployment as base
from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand

PRICE_PROOFS = (
    "price_lt_lte_boundary_test",
    "price_filter_before_pagination_test",
    "price_evidence_active_phase_test",
    "budget_followup_live_test",
    "backend_child_event_visibility_test",
    "area_event_membership_test",
    "inactive_phase_visibility_test",
)


def fixture_id(prefix: str, value: str) -> str:
    from uuid import UUID

    return str(UUID(hashlib.md5((prefix + value).encode(), usedforsecurity=False).hexdigest()))


def expected_visibility_requests() -> list[dict[str, Any]]:
    requests = []
    for state in ("DRAFT", "PENDING_APPROVAL", "CANCELLED"):
        event = fixture_id("ai-hidden-fixture-", state)
        area = fixture_id("price-area-", event)
        ticket = fixture_id("price-type-", event)
        phase = fixture_id("price-phase-", event)
        for path in (
            f"/api/v1/events/{event}/areas",
            f"/api/v1/areas/{area}",
            f"/api/v1/areas/{area}/seats",
            f"/api/v1/events/{event}/ticket-types",
            f"/api/v1/ticket-types/{ticket}",
            f"/api/v1/events/{event}/sale-phases",
            f"/api/v1/sale-phases/{phase}",
            f"/api/v1/events/{event}/inventory",
            f"/api/v1/sale-phases/{phase}/inventory",
        ):
            requests.append({"method": "GET", "path": path, "status": 404})
    public = fixture_id("ai-public-search-fixture-", "1")
    for path, status in (
        (f"/api/v1/events/{public}/areas", 200),
        (f"/api/v1/events/{public}/sale-phases", 200),
        (f"/api/v1/sale-phases/{fixture_id('price-draft-phase-', public)}", 404),
    ):
        requests.append({"method": "GET", "path": path, "status": status})
    return requests


def enable_price(directory: Path) -> None:
    path = directory / "implementation_gates.yaml"
    gates = yaml.safe_load(path.read_text("utf-8"))
    gates["gates"]["PUBLISHED-CHILD"].update(
        status="PASS", scope="Local price search only; all event-child tools remain disabled"
    )
    path.write_text(yaml.safe_dump(gates, allow_unicode=True), encoding="utf-8")


async def verify(backend: str, report_path: Path) -> None:
    await base.verify(backend, report_path)
    report = json.loads(report_path.read_text("utf-8"))
    visibility = []
    with tempfile.TemporaryDirectory() as temporary:
        config = Path(temporary)
        base.write_documents(config)
        enable_price(config)

        class TracedTransport(SafeBackendTransport):
            async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
                report["business_http_trace"].append({"method": "GET", "path": path})
                return await super().get(path, **kwargs)

        gateway = ReadOnlyToolGateway(
            config / "runtime_tool_registry.yaml",
            config / "implementation_gates.yaml",
            TracedTransport(backend),
        )
        assert gateway.available_names() == ("search_events",)
        args = {
            "q": "AI integration public",
            "maxPrice": "500000",
            "priceComparison": "LT",
            "size": 20,
        }
        below = await gateway.execute("search_events", args)
        expected = {
            "ai-integration-public-1",
            *(f"ai-integration-public-{n}" for n in range(10, 26)),
        }
        assert {r["slug"] for r in below["data"]} == expected, below
        at_most = await gateway.execute("search_events", {**args, "priceComparison": "LTE"})
        assert {r["slug"] for r in at_most["data"]} == expected | {"ai-integration-public-2"}
        page0 = await gateway.execute("search_events", {**args, "size": 5})
        page1 = await gateway.execute("search_events", {**args, "size": 5, "page": 1})
        assert page0["pagination"]["totalElements"] == 17
        assert not ({r["id"] for r in page0["data"]} & {r["id"] for r in page1["data"]})
        first = next(r for r in below["data"] if r["slug"] == "ai-integration-public-1")
        assert str(first["price"]) in ("499999", "499999.0", "499999.00")
        assert first["salePhaseId"] == fixture_id("price-phase-", first["id"])
        chat = ChatUseCase(RuleBasedVietnameseNLU(), gateway)
        initial = await chat.handle(ChatCommand(message="Tìm sự kiện ở Hồ Chí Minh dưới 500k"))
        followup = await chat.handle(ChatCommand(message="mỗi vé", previous_state=initial.state))
        assert followup.tool_called == "search_events" and followup.events
        assert all(e.price is not None and Decimal(e.price) < 500000 for e in followup.events)
        async with httpx.AsyncClient(base_url=backend, timeout=5, trust_env=False) as client:

            async def read(path: str, denied: bool = False):
                response = await client.get(path)
                visibility.append({"method": "GET", "path": path, "status": response.status_code})
                assert response.status_code == (404 if denied else 200), (path, response.text[:200])
                return response.json().get("data")

            for status in ("DRAFT", "PENDING_APPROVAL", "CANCELLED"):
                event = fixture_id("ai-hidden-fixture-", status)
                area = fixture_id("price-area-", event)
                ticket = fixture_id("price-type-", event)
                phase = fixture_id("price-phase-", event)
                for path in (
                    f"/api/v1/events/{event}/areas",
                    f"/api/v1/areas/{area}",
                    f"/api/v1/areas/{area}/seats",
                    f"/api/v1/events/{event}/ticket-types",
                    f"/api/v1/ticket-types/{ticket}",
                    f"/api/v1/events/{event}/sale-phases",
                    f"/api/v1/sale-phases/{phase}",
                    f"/api/v1/events/{event}/inventory",
                    f"/api/v1/sale-phases/{phase}/inventory",
                ):
                    await read(path, denied=True)
            areas = await read(f"/api/v1/events/{first['id']}/areas")
            assert len(areas) == 1 and areas[0]["id"] == fixture_id("price-area-", first["id"])
            phases = await read(f"/api/v1/events/{first['id']}/sale-phases")
            assert {p["id"] for p in phases} == {first["salePhaseId"]}
            await read(
                f"/api/v1/sale-phases/{fixture_id('price-draft-phase-', first['id'])}", denied=True
            )
    report["feature"] = "public-price-search"
    report["proofs"].update({name: True for name in PRICE_PROOFS})
    report["child_visibility_requests"] = visibility
    report["price_fixture_sha256"] = hashlib.sha256(
        (base.ROOT / "tests/fixtures/public_price_search.sql").read_bytes()
    ).hexdigest()
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Public price, pagination, evidence and anonymous child visibility passed.")


def prepare(report_path: Path, output: Path) -> None:
    report = json.loads(report_path.read_text("utf-8"))
    if (
        report.get("feature") != "public-price-search"
        or any(report.get("proofs", {}).get(p) is not True for p in PRICE_PROOFS)
        or report.get("child_visibility_requests") != expected_visibility_requests()
        or report.get("price_fixture_sha256")
        != hashlib.sha256(
            (base.ROOT / "tests/fixtures/public_price_search.sql").read_bytes()
        ).hexdigest()
    ):
        raise ValueError("Missing price/visibility evidence; price search stays disabled")
    base.prepare(report_path, output)
    enable_price(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    check = actions.add_parser("verify")
    check.add_argument("--backend", required=True)
    check.add_argument("--report", required=True, type=Path)
    deploy = actions.add_parser("prepare")
    deploy.add_argument("--report", required=True, type=Path)
    deploy.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "verify":
        asyncio.run(verify(args.backend, args.report))
    else:
        prepare(args.report, args.output)
