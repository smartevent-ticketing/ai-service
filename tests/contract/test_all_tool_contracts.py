"""Every shipped business tool must fail closed and enforce its projection."""

from pathlib import Path

import pytest

from conftest import ROOT, SpyTransport
from smartevent_ai.adapters.outbound.read_only_gateway import ReadOnlyToolGateway
from smartevent_ai.domain.errors import ContractViolation, ToolUnavailable

TOOLS = (
    "search_events",
    "get_event_details",
    "get_event_areas",
    "get_ticket_types",
    "get_sale_phases",
    "get_event_inventory",
    "get_available_seats",
    "get_active_reservation",
    "get_reservation",
    "get_my_orders",
    "get_order",
    "get_payment_status",
    "get_my_tickets",
    "get_refund_review",
)
UID = "08c25afc-f9c9-4db0-aab7-02c779779d6c"


def shipped(transport: SpyTransport) -> ReadOnlyToolGateway:
    return ReadOnlyToolGateway(
        Path(ROOT / "configs/runtime_tool_registry.yaml"),
        Path(ROOT / "configs/implementation_gates.yaml"),
        transport,
    )


@pytest.mark.parametrize("name", TOOLS)
@pytest.mark.asyncio
async def test_every_tool_disabled_before_argument_validation_or_io(name: str) -> None:
    transport = SpyTransport()
    gateway = shipped(transport)
    assert set(gateway.tools) == set(TOOLS)
    with pytest.raises(ToolUnavailable):
        await gateway.execute(name, {})
    assert transport.calls == []


@pytest.mark.parametrize("name", TOOLS)
def test_every_tool_required_fields_and_sensitive_projection(name: str) -> None:
    gateway = shipped(SpyTransport())
    tool = gateway.tools[name]
    row = {
        key: (UID if key == "id" or key.endswith("Id") else "Example")
        for key in tool["response_schema"]["required"]
    }
    for field in ("price", "availableQuantity"):
        if field in row:
            row[field] = 0
    if name in ("search_events", "get_event_details"):
        row["status"] = "PUBLISHED"
    elif name == "get_available_seats":
        row["status"] = "AVAILABLE"
    row.update(qrCodeBase64="SECRET_QR", token="SECRET_TOKEN", userId="SECRET_OWNER")
    projected = gateway._project_row(tool, row)
    assert "SECRET" not in str(projected)
    for field in tool["response_schema"]["required"]:
        missing = {key: value for key, value in row.items() if key != field}
        with pytest.raises(ContractViolation):
            gateway._project_row(tool, missing)
