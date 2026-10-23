from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


class SpyTransport:
    def __init__(self, response: dict[str, Any] | None = None):
        self.response = response if response is not None else {"success": True, "data": {}}
        self.calls: list[tuple[str, dict[str, Any], int, int]] = []

    async def get(
        self, path: str, *, query: dict[str, Any], max_bytes: int, timeout_ms: int
    ) -> dict[str, Any]:
        self.calls.append((path, query, max_bytes, timeout_ms))
        return self.response


@pytest.fixture
def approved_registry(tmp_path: Path) -> tuple[Path, Path]:
    registry = yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())
    gates = yaml.safe_load((ROOT / "configs/implementation_gates.yaml").read_text())
    for t in registry["tools"]:
        if t["name"] in ("search_events", "get_event_details"):
            t["enabled"] = True
    gates["gates"]["PUBLIC-SEARCH"]["status"] = "PASS"
    gates["gates"]["PUBLIC-DETAIL"]["status"] = "PASS"
    gates["gates"]["RUNTIME-READONLY"]["status"] = "PASS"
    p = tmp_path / "registry.yaml"
    g = tmp_path / "gates.yaml"
    p.write_text(yaml.safe_dump(registry))
    g.write_text(yaml.safe_dump(gates))
    return p, g
