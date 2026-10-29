"""Verify real anonymous search, then prepare a scoped local deployment (never defaults)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
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
PROOFS = (
    "anonymous_published_search_test",
    "response_projection_contract_test",
    "live_tool_executor_allowlist_test",
    "zero_business_write_spy",
    "no_side_effect_get_test",
    "application_event_links_test",
)


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        *sorted((ROOT / "configs").rglob("*.yaml")),
        *sorted((ROOT / "scripts").glob("*.py")),
        *sorted((ROOT / "scripts").glob("*.ps1")),
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
    for name in ("PUBLIC-SEARCH", "RUNTIME-READONLY"):
        gates["gates"][name]["status"] = "PASS"
        gates["gates"][name]["scope"] = "Local deployment: search_events only"
    return registry, gates


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


def prepare(report_path: Path, output: Path) -> None:
    report = json.loads(report_path.read_text("utf-8"))
    before = report.get("database_snapshot_before")
    if (
        report.get("scope") != "local-public-search-only"
        or report.get("source_sha256") != source_fingerprint()
        or not isinstance(before, str)
        or len(before) != 64
        or any(c not in "0123456789abcdef" for c in before)
        or report.get("database_snapshot_after") != before
        or any(report.get("proofs", {}).get(name) is not True for name in PROOFS)
        or not report.get("business_http_trace")
        or any(
            c != {"method": "GET", "path": "/api/v1/events"} for c in report["business_http_trace"]
        )
    ):
        raise ValueError("Incomplete, stale or failed live evidence; deployment remains disabled")
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
