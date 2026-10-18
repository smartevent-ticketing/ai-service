from typing import Any

import httpx
import pytest

from smartevent_ai.adapters.outbound.safe_transport import SafeBackendTransport
from smartevent_ai.domain.errors import BackendUnavailable, ContractViolation


@pytest.mark.parametrize(
    "origin",
    [
        "http://a/path",
        "file:///etc/passwd",
        "https://user:pass@example.com",
        "http://ok/?q=1",
        "http://ok/#x",
        "ftp://localhost",
    ],
)
def test_transport_rejects_unsafe_origin(origin: str) -> None:
    with pytest.raises(ContractViolation):
        SafeBackendTransport(origin)


@pytest.mark.asyncio
async def test_transport_redirect_and_size_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"Location": "http://evil.invalid/"})

        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    with pytest.raises(BackendUnavailable):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=100, timeout_ms=100
        )


def test_transport_rejects_path_escape() -> None:
    # Avoid network by checking URL/host constraints on construction.
    with pytest.raises(ContractViolation):
        SafeBackendTransport("http://127.0.0.1:8080/prefix")


@pytest.mark.asyncio
async def test_transport_rejects_response_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient
    requests: list[httpx.Request] = []

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"success": True, "data": {"payload": "x" * 1000}},
                headers={"content-type": "application/json"},
            )

        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    with pytest.raises(BackendUnavailable):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=80, timeout_ms=1000
        )
    assert requests[0].method == "GET"
    assert requests[0].url.host == "127.0.0.1"


@pytest.mark.asyncio
async def test_transport_success_is_same_origin_get(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient
    requests: list[httpx.Request] = []

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"success": True, "data": {"content": []}},
                headers={"content-type": "application/json"},
            )

        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    data = await SafeBackendTransport("https://backend.example.org").get(
        "/api/v1/events",
        query={"page": 0, "size": 10},
        max_bytes=1000,
        timeout_ms=1000,
    )
    assert data["success"] is True
    assert requests[0].method == "GET"
    assert requests[0].url.host == "backend.example.org"
    assert requests[0].url.params["page"] == "0"
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize(
    "route", ["/api/v1/../admin", "https://other.org/api/v1/events", "/api/v1//events"]
)
@pytest.mark.asyncio
async def test_transport_rejects_invalid_paths_before_network(route: str) -> None:
    with pytest.raises(ContractViolation):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            route, query={}, max_bytes=1000, timeout_ms=1000
        )


@pytest.mark.asyncio
async def test_transport_rejects_non_json_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient

    def substitute(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=b'{"success":true}', headers={"content-type": "text/plain"}
            )

        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", substitute)
    with pytest.raises(BackendUnavailable):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=1000, timeout_ms=1000
        )


@pytest.mark.parametrize("max_bytes, timeout_ms", [(0, 1000), (1000, 0), (1000, 20_000)])
@pytest.mark.asyncio
async def test_transport_rejects_invalid_resource_bounds(max_bytes: int, timeout_ms: int) -> None:
    with pytest.raises(ContractViolation):
        await SafeBackendTransport("http://127.0.0.1:8080").get(
            "/api/v1/events", query={}, max_bytes=max_bytes, timeout_ms=timeout_ms
        )
