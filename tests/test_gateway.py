from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml

from conftest import ROOT, SpyTransport
from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.domain.errors import BackendUnavailable, ContractViolation, ToolUnavailable

UID = "08c25afc-f9c9-4db0-aab7-02c779779d6c"


def event(**updates: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": UID,
        "name": "Sample",
        "slug": "sample",
        "status": "PUBLISHED",
        "venue": {"name": "National Venue"},
        "qrCodeBase64": "SENSITIVE",
    }
    data.update(updates)
    return data


def test_no_tools_are_enabled_in_shipped_contract() -> None:
    gateway = ReadOnlyToolGateway(
        ROOT / "configs/runtime_tool_registry.yaml",
        ROOT / "configs/implementation_gates.yaml",
        SpyTransport(),
    )
    assert gateway.available_names() == ()
    assert all(t["method"] == "GET" and not t["enabled"] for t in gateway.tools.values())


@pytest.mark.asyncio
async def test_default_disabled_means_zero_business_http_calls() -> None:
    spy = SpyTransport()
    gateway = ReadOnlyToolGateway(
        ROOT / "configs/runtime_tool_registry.yaml", ROOT / "configs/implementation_gates.yaml", spy
    )
    for name in ("search_events", "get_event_details", "get_my_tickets", "create_reservation"):
        with pytest.raises(ToolUnavailable):
            await gateway.execute(name, {"id": UID})
    assert spy.calls == []


def test_enabled_but_gate_unapproved_fails_on_boot(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    config["tools"][0]["enabled"] = True
    path = tmp_path / "unapproved.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())


def test_get_or_mutation_tools_rejected_at_boot(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    config["tools"][0]["method"] = "POST"
    path = tmp_path / "mutation.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())


@pytest.mark.asyncio
async def test_projection_venue_and_secret(approved_registry: tuple[Path, Path]) -> None:
    response = {
        "success": True,
        "data": {
            "content": [event()],
            "page": 0,
            "size": 10,
            "totalElements": 1,
            "totalPages": 1,
            "last": True,
        },
    }
    spy = SpyTransport(response)
    gateway = ReadOnlyToolGateway(*approved_registry, spy)
    projected = await gateway.execute("search_events", {"page": 0, "size": 10})
    assert projected["data"][0]["venueName"] == "National Venue"
    assert "qrCodeBase64" not in str(projected)
    assert projected["result_complete"] is True
    assert spy.calls[0][0] == "/api/v1/events"
    assert spy.calls[0][2] == 262144


@pytest.mark.asyncio
async def test_missing_required_response_rejected(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry, SpyTransport({"success": True, "data": {"status": "PUBLISHED"}})
    )
    with pytest.raises(ContractViolation):
        await gateway.execute("get_event_details", {"id": UID})


@pytest.mark.asyncio
async def test_unpublished_rejected(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry, SpyTransport({"success": True, "data": event(status="DRAFT")})
    )
    with pytest.raises(ContractViolation):
        await gateway.execute("get_event_details", {"id": UID})


@pytest.mark.asyncio
async def test_preserves_pagination(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry,
        SpyTransport(
            {
                "success": True,
                "data": {
                    "content": [event() for _ in range(10)],
                    "page": 0,
                    "size": 10,
                    "totalElements": 10000,
                    "totalPages": 1000,
                    "last": False,
                },
            }
        ),
    )
    result = await gateway.execute("search_events", {"page": 0, "size": 10})
    assert result["has_more"] is True
    assert result["result_complete"] is False
    assert result["pagination"]["totalElements"] == 10000


@pytest.mark.asyncio
async def test_missing_page_metadata_fails(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry, SpyTransport({"success": True, "data": {"content": [event()]}})
    )
    with pytest.raises(ContractViolation):
        await gateway.execute("search_events", {"page": 0, "size": 10})


@pytest.mark.asyncio
async def test_argument_injection_rejected_without_network(
    approved_registry: tuple[Path, Path],
) -> None:
    spy = SpyTransport()
    gateway = ReadOnlyToolGateway(*approved_registry, spy)
    for arg in (
        {"id": "../../admin"},
        {"id": UID, "url": "http://evil.invalid"},
        {"id": UID, "page": 0},
        {"id": "something"},
    ):
        with pytest.raises(ContractViolation):
            await gateway.execute("get_event_details", arg)
    assert spy.calls == []


@pytest.mark.asyncio
async def test_backend_error_fails(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry, SpyTransport({"success": False, "data": event()})
    )
    with pytest.raises(BackendUnavailable):
        await gateway.execute("get_event_details", {"id": UID})


def test_projection_rejects_missing_ticket_credentials_but_keeps_only_allowed_fields() -> None:
    gateway = ReadOnlyToolGateway(
        ROOT / "configs/runtime_tool_registry.yaml",
        ROOT / "configs/implementation_gates.yaml",
        SpyTransport(),
    )
    ticket = gateway.tools["get_my_tickets"]
    item = ReadOnlyToolGateway._project_row(
        ticket,
        {
            "id": UID,
            "eventId": UID,
            "status": "ISSUED",
            "qrCodeBase64": "SECRET",
            "token": "SECRET",
        },
    )
    assert "SECRET" not in str(item)
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway._project_row(ticket, {"qrCodeBase64": "SECRET"})


def test_seats_filtered_before_cap() -> None:
    gateway = ReadOnlyToolGateway(
        ROOT / "configs/runtime_tool_registry.yaml",
        ROOT / "configs/implementation_gates.yaml",
        SpyTransport(),
    )
    tool = deepcopy(gateway.tools["get_available_seats"])
    tool["max_results"] = 1
    seats = [
        {"id": str(uuid4()), "eventAreaId": UID, "status": "HELD"},
        {"id": str(uuid4()), "eventAreaId": UID, "status": "AVAILABLE"},
        {"id": str(uuid4()), "eventAreaId": UID, "status": "AVAILABLE"},
    ]
    result = gateway.project(tool, seats)
    assert result["filtered_total"] == 2
    assert result["returned_count"] == 1
    assert result["capped_by_adapter"] is True
    assert result["result_complete"] is False


@pytest.mark.asyncio
async def test_runtime_gate_required_even_if_tool_passes(
    tmp_path: Path, approved_registry: tuple[Path, Path]
) -> None:
    reg, gates = approved_registry
    d = yaml.safe_load(gates.read_text())
    d["gates"]["RUNTIME-READONLY"]["status"] = "BLOCKED"
    gates.write_text(yaml.safe_dump(d))
    spy = SpyTransport()
    gateway = ReadOnlyToolGateway(reg, gates, spy)
    assert gateway.available_names() == ()
    with pytest.raises(ToolUnavailable):
        await gateway.execute("search_events", {})
    assert spy.calls == []


@pytest.mark.asyncio
async def test_private_tool_cannot_be_enabled_even_with_gates(tmp_path: Path) -> None:
    conf = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    gates = yaml.safe_load((ROOT / "configs/implementation_gates.yaml").read_text())
    for t in conf["tools"]:
        if t["name"] == "get_my_orders":
            t["enabled"] = True
    gates["gates"]["PRIVATE-SELF-AUTH"]["status"] = "PASS"
    x = tmp_path / "tools.yaml"
    y = tmp_path / "gates.yaml"
    x.write_text(yaml.safe_dump(conf))
    y.write_text(yaml.safe_dump(gates))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(x, y, SpyTransport())


@pytest.mark.asyncio
async def test_bad_page_last_value_rejected(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry,
        SpyTransport(
            {
                "success": True,
                "data": {
                    "content": [event()],
                    "page": 0,
                    "size": 10,
                    "totalElements": 100,
                    "totalPages": 10,
                    "last": "no",
                },
            }
        ),
    )
    with pytest.raises(ContractViolation):
        await gateway.execute("search_events", {})


@pytest.mark.asyncio
async def test_backend_search_does_not_accept_draft_response(
    approved_registry: tuple[Path, Path],
) -> None:
    response = {
        "success": True,
        "data": {
            "content": [event(status="DRAFT")],
            "page": 0,
            "size": 10,
            "totalElements": 1,
            "totalPages": 1,
            "last": True,
        },
    }
    gateway = ReadOnlyToolGateway(*approved_registry, SpyTransport(response))
    with pytest.raises(ContractViolation):
        await gateway.execute("search_events", {})


@pytest.mark.asyncio
async def test_contradictory_last_flag_rejected(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry,
        SpyTransport(
            {
                "success": True,
                "data": {
                    "content": [event()],
                    "page": 0,
                    "size": 10,
                    "totalElements": 100,
                    "totalPages": 10,
                    "last": True,
                },
            }
        ),
    )
    with pytest.raises(ContractViolation):
        await gateway.execute("search_events", {"page": 0, "size": 10})


@pytest.mark.asyncio
async def test_total_pages_must_match_total_and_size(approved_registry: tuple[Path, Path]) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry,
        SpyTransport(
            {
                "success": True,
                "data": {
                    "content": [event()],
                    "page": 0,
                    "size": 10,
                    "totalElements": 11,
                    "totalPages": 99,
                    "last": False,
                },
            }
        ),
    )
    with pytest.raises(ContractViolation):
        await gateway.execute("search_events", {"page": 0, "size": 10})


@pytest.mark.asyncio
async def test_non_first_page_is_never_globally_complete(
    approved_registry: tuple[Path, Path],
) -> None:
    gateway = ReadOnlyToolGateway(
        *approved_registry,
        SpyTransport(
            {
                "success": True,
                "data": {
                    "content": [event()],
                    "page": 1,
                    "size": 10,
                    "totalElements": 11,
                    "totalPages": 2,
                    "last": True,
                },
            }
        ),
    )
    result = await gateway.execute("search_events", {"page": 1, "size": 10})
    assert result["has_previous"] is True
    assert result["has_more"] is False
    assert result["result_complete"] is False


def test_registry_global_enforcement_must_fail_closed(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    config["enforcement"]["deny_redirects"] = False
    path = tmp_path / "unsafe.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())


def test_registry_transport_policy_cannot_enable_retry(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    config["tools"][0]["retry_policy"] = "ONCE"
    path = tmp_path / "unsafe.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())


def test_registry_rejects_non_readonly_and_bad_byte_cap(tmp_path: Path) -> None:
    base = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    bad_access = deepcopy(base)
    bad_access["business_access"] = "READ_WRITE"
    first = tmp_path / "bad_access.yaml"
    first.write_text(yaml.safe_dump(bad_access))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(first, ROOT / "configs/implementation_gates.yaml", SpyTransport())

    bad_cap = deepcopy(base)
    bad_cap["enforcement"]["max_response_bytes"] = 0
    second = tmp_path / "bad_cap.yaml"
    second.write_text(yaml.safe_dump(bad_cap))
    with pytest.raises(ContractViolation):
        ReadOnlyToolGateway(second, ROOT / "configs/implementation_gates.yaml", SpyTransport())


def test_registry_rejects_bad_tool_contract_shapes(tmp_path: Path) -> None:
    base = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    variants = []
    missing = deepcopy(base)
    del missing["tools"][0]["timeout_ms"]
    variants.append(missing)
    bad_name = deepcopy(base)
    bad_name["tools"][0]["name"] = "BAD NAME"
    variants.append(bad_name)
    bad_endpoint = deepcopy(base)
    bad_endpoint["tools"][0]["endpoint"] = "https://evil.invalid/api/v1/events"
    variants.append(bad_endpoint)
    bad_projection = deepcopy(base)
    bad_projection["tools"][0]["response"]["projection"] = "RAW"
    variants.append(bad_projection)

    for index, config in enumerate(variants):
        path = tmp_path / f"bad_{index}.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(ContractViolation):
            ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())


def test_empty_page_metadata_and_unknown_shape() -> None:
    gateway = ReadOnlyToolGateway(
        ROOT / "configs/runtime_tool_registry.yaml",
        ROOT / "configs/implementation_gates.yaml",
        SpyTransport(),
    )
    tool = deepcopy(gateway.tools["search_events"])
    result = gateway.project(
        tool,
        {"content": [], "page": 0, "size": 10, "totalElements": 0, "totalPages": 0, "last": True},
    )
    assert result["result_complete"] is True

    tool["response"]["result_shape"] = "mystery"
    with pytest.raises(ContractViolation):
        gateway.project(tool, [])


def test_registry_rejects_non_default_deny_and_raw_projection(tmp_path: Path) -> None:
    base = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    variants = []
    bad_default = deepcopy(base)
    bad_default["enforcement"]["default"] = "allow"
    variants.append(bad_default)
    bad_projection_mode = deepcopy(base)
    bad_projection_mode["enforcement"]["response_projection_mode"] = "raw"
    variants.append(bad_projection_mode)
    bad_retry_default = deepcopy(base)
    bad_retry_default["enforcement"]["deny_request_retries_by_default"] = False
    variants.append(bad_retry_default)
    bad_safety = deepcopy(base)
    bad_safety["tools"][0]["safety"]["validated_origin_required"] = False
    variants.append(bad_safety)

    for index, config in enumerate(variants):
        path = tmp_path / f"policy_{index}.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(ContractViolation):
            ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())


def test_registry_rejects_invalid_response_allowlist(tmp_path: Path) -> None:
    base = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    variants = []
    duplicate_fields = deepcopy(base)
    duplicate_fields["tools"][0]["response"]["fields"].append("id")
    variants.append(duplicate_fields)
    invalid_mapping = deepcopy(base)
    invalid_mapping["tools"][0]["response"]["field_mappings"] = {"notAllowed": "venue.name"}
    variants.append(invalid_mapping)
    bad_shape = deepcopy(base)
    bad_shape["tools"][0]["response"]["result_shape"] = "stream"
    variants.append(bad_shape)

    for index, config in enumerate(variants):
        path = tmp_path / f"response_{index}.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(ContractViolation):
            ReadOnlyToolGateway(path, ROOT / "configs/implementation_gates.yaml", SpyTransport())
