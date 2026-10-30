"""Verify real anonymous search, then prepare a scoped local deployment (never defaults)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import yaml

from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport
from smartevent_ai.domain.errors import ContractViolation, ToolUnavailable
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand

ROOT = Path(__file__).resolve().parents[1]
BACKEND_JAR = ROOT.parent / "smartevent-backend/build/libs/smart-event-backend-0.0.1-SNAPSHOT.jar"
PROOFS = (
    "anonymous_published_search_test",
    "response_projection_contract_test",
    "live_tool_executor_allowlist_test",
    "zero_business_write_spy",
    "no_side_effect_get_test",
    "application_event_links_test",
    "date_range_and_offset_test",
    "price_lt_lte_and_inactive_child_test",
    "search_child_area_and_inventory_membership_test",
    "search_budget_to_event_cards_test",
    "date_filter_boundaries_test",
)


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        *sorted((ROOT / "configs").rglob("*.yaml")),
        *sorted((ROOT / "scripts").rglob("*.py")),
        *sorted((ROOT / "scripts").rglob("*.ps1")),
        *sorted((ROOT / "tests/fixtures").rglob("*.sql")),
    ]
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def candidate_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    registry = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text("utf-8"))
    gates = yaml.safe_load((ROOT / "configs/implementation_gates.yaml").read_text("utf-8"))
    for tool in registry["tools"]:
        tool["enabled"] = tool["name"] == "search_events"
    for name in ("PUBLIC-SEARCH", "RUNTIME-READONLY", "PUBLISHED-CHILD"):
        gates["gates"][name]["status"] = "PASS"
        gates["gates"][name]["scope"] = "Local deployment: search_events only"
    return registry, gates


async def verify_filters(gateway: ReadOnlyToolGateway) -> None:
    """Requires the dedicated SQL fixture; never seed or mutate a live database here."""
    from datetime import timedelta, timezone

    prefix = {"q": "AI_FILTER_", "size": 20}
    inclusive = await gateway.execute(
        "search_events", {**prefix, "maxPrice": "200000", "priceComparison": "LTE"}
    )
    strict = await gateway.execute(
        "search_events", {**prefix, "maxPrice": "200000", "priceComparison": "LT"}
    )
    assert {r["slug"] for r in inclusive["data"]} == {"ai-filter-lt", "ai-filter-eq"}
    assert {r["slug"] for r in strict["data"]} == {"ai-filter-lt"}
    assert inclusive["result_complete"] and strict["result_complete"]
    assert all(
        Decimal(str(r["price"])) <= 200000
        and r["currency"] == "VND"
        and r["ticketTypeId"]
        and r["salePhaseId"]
        and r["priceObservedAt"]
        and r["priceBasis"] == "TICKET_FACE_VALUE"
        for r in inclusive["data"]
    )
    unfiltered = await gateway.execute("search_events", prefix)
    by_slug = {r["slug"]: r for r in unfiltered["data"]}
    assert "ai-filter-hidden" not in by_slug
    assert Decimal(str(by_slug["ai-filter-lt"]["price"])) == 100000
    for slug in (
        "inactive",
        "type-inactive",
        "sold",
        "future",
        "expired",
        "bad-area",
        "bad-counter",
    ):
        assert by_slug[f"ai-filter-{slug}"].get("price") is None
    start = datetime.fromisoformat(by_slug["ai-filter-lt"]["startTime"].replace("Z", "+00:00"))
    stop = datetime.fromisoformat(by_slug["ai-filter-eq"]["startTime"].replace("Z", "+00:00"))
    for zone in (UTC, timezone(timedelta(hours=7))):
        dated = await gateway.execute(
            "search_events",
            {
                **prefix,
                "startFrom": start.astimezone(zone).isoformat(),
                "startBefore": stop.astimezone(zone).isoformat(),
            },
        )
        assert [r["slug"] for r in dated["data"]] == ["ai-filter-lt"]
    chat = await ChatUseCase(RuleBasedVietnameseNLU(), gateway).handle(
        ChatCommand(message="Tìm AI_FILTER_ 2 vé ở Hồ Chí Minh tối đa 400 nghìn tổng")
    )
    assert chat.tool_called == "search_events" and chat.events
    assert {e.slug for e in chat.events} == {"ai-filter-lt", "ai-filter-eq"}


def write_documents(directory: Path) -> None:
    registry, gates = candidate_documents()
    for name, data in (
        ("runtime_tool_registry.yaml", registry),
        ("implementation_gates.yaml", gates),
    ):
        (directory / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


async def verify(base_url: str, report_path: Path) -> None:
    """A temporary candidate is tested against a disposable, seeded Spring backend."""
    calls: list[dict[str, str]] = []
    original = httpx.AsyncClient.stream

    def trace_stream(
        client: httpx.AsyncClient, method: str, url: Any, *args: Any, **kwargs: Any
    ) -> Any:
        if method != "GET" or str(url) != "/api/v1/events" or "Authorization" in client.headers:
            raise AssertionError("Unexpected business request")
        calls.append({"method": method, "path": str(url)})
        return original(client, method, url, *args, **kwargs)

    httpx.AsyncClient.stream = trace_stream  # type: ignore[method-assign]
    try:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            write_documents(candidate)
            transport = SafeBackendTransport(base_url)
            gateway = ReadOnlyToolGateway(
                candidate / "runtime_tool_registry.yaml",
                candidate / "implementation_gates.yaml",
                transport,
            )
            assert gateway.available_names() == ("search_events",)
            result = await gateway.execute("search_events", {"page": 0, "size": 10})
            assert len(result["data"]) == 10 and result["has_more"]
            assert not result["result_complete"]
            allowed = set(gateway.tools["search_events"]["response"]["fields"])
            assert all(
                row["status"] == "PUBLISHED" and set(row) <= allowed for row in result["data"]
            )
            assert all("organizerId" not in row for row in result["data"])
            city = await gateway.execute("search_events", {"city": "Hồ Chí Minh", "size": 10})
            assert city["data"] and all(r["city"] == "Hồ Chí Minh" for r in city["data"])
            hidden = await gateway.execute("search_events", {"q": "AI_GATE_HIDDEN", "size": 10})
            assert hidden["data"] == [] and hidden["result_complete"]
            empty = await gateway.execute("search_events", {"q": "AI_GATE_NO_MATCH_49281"})
            assert empty["data"] == [] and empty["result_complete"]
            page = await gateway.execute("search_events", {"page": 1, "size": 10})
            assert page["has_previous"] and not page["result_complete"]
            assert not ({r["id"] for r in page["data"]} & {r["id"] for r in result["data"]})
            chat_result = await ChatUseCase(RuleBasedVietnameseNLU(), gateway).handle(
                ChatCommand(message="Tìm sự kiện ở Hồ Chí Minh")
            )
            assert chat_result.tool_called == "search_events" and chat_result.event_links
            assert {link.slug for link in chat_result.event_links} == {
                row["slug"] for row in city["data"]
            }
            await verify_filters(gateway)
            # Exact fixture boundaries prove filtering occurs before pagination.
            first, second = result["data"][:2]
            date_args = {"startFrom": first["startTime"], "startBefore": second["startTime"]}
            dated = await gateway.execute("search_events", date_args)
            assert [row["id"] for row in dated["data"]] == [first["id"]]
            assert dated["result_complete"]
            excluded = await gateway.execute("search_events", {"q": "AI_GATE_HIDDEN", **date_args})
            assert excluded["data"] == []
            month = datetime.fromisoformat(first["startTime"].replace("Z", "+00:00"))
            monthly = await ChatUseCase(RuleBasedVietnameseNLU(), gateway).handle(
                ChatCommand(message=f"Tìm sự kiện tháng {month.month}/{month.year}")
            )
            assert monthly.tool_called == "search_events" and monthly.events
            assert monthly.state.start_from is not None and monthly.state.start_before is not None
            assert all(
                monthly.state.start_from
                <= datetime.fromisoformat(e.start_time.replace("Z", "+00:00"))
                < monthly.state.start_before
                for e in monthly.events
            )
            before = len(calls)
            for name in [n for n in gateway.tools if n != "search_events"] + ["create_order"]:
                try:
                    await gateway.execute(name, {})
                except ToolUnavailable:
                    pass
                else:
                    raise AssertionError("Unexpected enabled tool")
            for path in ("/api/v1/payments/vnpay/ipn", "/api/v1/events/../orders"):
                try:
                    await transport.get(path, query={}, max_bytes=1024, timeout_ms=1000)
                except ContractViolation:
                    pass
                else:
                    raise AssertionError("Unsafe GET accepted")
            assert len(calls) == before
    finally:
        httpx.AsyncClient.stream = original  # type: ignore[method-assign]
    report = {
        "scope": "local-public-search-only",
        "verified_at": datetime.now(UTC).isoformat(),
        "source_sha256": source_fingerprint(),
        "backend_under_test": base_url,
        "proofs": {name: True for name in PROOFS},
        "business_http_trace": calls,
        "database_snapshot_before": None,
        "database_snapshot_after": None,
        "note": "Not deployable until independent fixture database snapshots match.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Live anonymous search checks passed; independent DB snapshot verification pending.")


def validate_report(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text("utf-8-sig"))
    before = report.get("database_snapshot_before")
    backend_hash = report.get("backend_jar_sha256")
    if (
        report.get("scope") != "local-public-search-only"
        or report.get("source_sha256") != source_fingerprint()
        or not isinstance(before, str)
        or len(before) != 64
        or any(c not in "0123456789abcdef" for c in before)
        or report.get("database_snapshot_after") != before
        or not isinstance(backend_hash, str)
        or len(backend_hash) != 64
        or any(c not in "0123456789abcdef" for c in backend_hash)
        or any(report.get("proofs", {}).get(name) is not True for name in PROOFS)
        or not report.get("business_http_trace")
        or any(
            c != {"method": "GET", "path": "/api/v1/events"} for c in report["business_http_trace"]
        )
    ):
        raise ValueError("Incomplete, stale or failed live evidence; deployment remains disabled")
    return report


def validate_deployment(directory: Path) -> None:
    """Reject stale evidence or edits that widen a verified search-only profile."""
    report = validate_report(directory / "public_search_evidence.json")
    if not BACKEND_JAR.is_file():
        raise ValueError("Verified backend JAR is missing")
    with BACKEND_JAR.open("rb") as stream:
        backend_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if backend_hash != report["backend_jar_sha256"]:
        raise ValueError("Backend JAR differs from the artifact verified by the search profile")
    backend_sources = BACKEND_JAR.parents[2] / "src/main"
    if any(
        p.is_file() and p.stat().st_mtime > BACKEND_JAR.stat().st_mtime
        for p in backend_sources.rglob("*")
    ):
        raise ValueError("Backend sources changed after bootJar; rebuild and verify again")
    registry, gates = candidate_documents()
    for name, expected in (
        ("runtime_tool_registry.yaml", registry),
        ("implementation_gates.yaml", gates),
    ):
        if yaml.safe_load((directory / name).read_text("utf-8")) != expected:
            raise ValueError("Search profile differs from verified permissions")
    for source in (ROOT / "configs").rglob("*"):
        if (
            source.is_file()
            and source.name not in ("runtime_tool_registry.yaml", "implementation_gates.yaml")
            and (directory / source.relative_to(ROOT / "configs")).read_bytes()
            != source.read_bytes()
        ):
            raise ValueError("Search profile has unverified policy configuration")


def prepare(report_path: Path, output: Path) -> None:
    validate_report(report_path)
    if output.exists():
        raise ValueError("Deployment directory must be new")
    shutil.copytree(ROOT / "configs", output)
    write_documents(output)
    (output / "public_search_evidence.json").write_bytes(report_path.read_bytes())
    print("Prepared reviewed local search deployment; shipped default configs remain disabled.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    check = actions.add_parser("verify")
    check.add_argument("--backend", required=True)
    check.add_argument("--report", type=Path, required=True)
    deploy = actions.add_parser("prepare")
    deploy.add_argument("--report", type=Path, required=True)
    deploy.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "verify":
        asyncio.run(verify(args.backend, args.report))
    else:
        prepare(args.report, args.output)


if __name__ == "__main__":
    main()
