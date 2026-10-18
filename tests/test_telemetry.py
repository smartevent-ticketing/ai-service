import json
import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.inbound.request_telemetry import RequestTelemetry


def test_request_logs_only_safe_metadata(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="smartevent_ai.requests"):
        response = client.post(
            "/api/v1/chat",
            json={"message": "SECRET_MESSAGE"},
            headers={"Authorization": "SECRET_TOKEN", "X-Request-ID": "SECRET_ID"},
        )
        client.get("/SECRET_PATH?token=SECRET_QUERY")
    trace_id = response.headers["x-request-id"]
    assert str(UUID(trace_id)) == trace_id
    records = [
        json.loads(row.message) for row in caplog.records if row.name == "smartevent_ai.requests"
    ]
    assert records[0]["trace_id"] == trace_id
    assert records[0]["route"] == "/api/v1/chat" and records[0]["status"] == 200
    assert records[1]["route"] == "unmatched"
    assert all(row["latency_ms"] >= 0 for row in records)
    assert "SECRET" not in json.dumps(records)


@pytest.mark.asyncio
async def test_non_http_telemetry_passthrough() -> None:
    calls = []

    async def app(scope, receive, send) -> None:
        calls.append(scope["type"])

    await RequestTelemetry(app)({"type": "lifespan"}, None, None)
    assert calls == ["lifespan"]
