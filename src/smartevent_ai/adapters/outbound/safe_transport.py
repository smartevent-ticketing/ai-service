"""HTTP transport with fixed origin, GET-only semantics and strict resource bounds."""

from __future__ import annotations

import json
import math
import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx

from smartevent_ai.adapters.outbound.route_policy import is_side_effect_route
from smartevent_ai.domain.errors import BackendUnavailable, ContractViolation
from smartevent_ai.domain.knowledge import MAX_JSON_DEPTH


class SafeBackendTransport:
    def __init__(self, origin: str):
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ContractViolation("Backend origin must be a single fixed http(s) origin")
        self.origin = origin.rstrip("/")

    async def get(
        self,
        path: str,
        *,
        query: dict[str, Any],
        max_bytes: int,
        timeout_ms: int,
    ) -> dict[str, Any]:
        if type(max_bytes) is not int or max_bytes < 1:
            raise ContractViolation("max_bytes must be a positive integer")
        if type(timeout_ms) is not int or not 100 <= timeout_ms <= 10_000:
            raise ContractViolation("timeout_ms outside approved bounds")
        if (
            not path.startswith("/api/v1/")
            or "//" in path
            or "\\" in path
            or ".." in path
            or "%" in path
            or "?" in path
            or "#" in path
            or is_side_effect_route(path)
        ):
            raise ContractViolation("Unsafe route")

        try:
            async with (
                asyncio.timeout(timeout_ms / 1000),
                httpx.AsyncClient(
                    base_url=self.origin,
                    follow_redirects=False,
                    trust_env=False,
                    headers={"Accept-Encoding": "identity"},
                    timeout=httpx.Timeout(timeout_ms / 1000),
                ) as client,
            ):
                async with client.stream("GET", path, params=query) as response:
                    if response.is_redirect or response.status_code != 200:
                        raise BackendUnavailable("Backend response denied or unavailable")
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    if content_type != "application/json" and not content_type.endswith("+json"):
                        raise BackendUnavailable("Backend response is not JSON")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise BackendUnavailable("Compressed backend payloads are not approved")
                    length = 0
                    parts: list[bytes] = []
                    async for chunk in response.aiter_bytes():
                        length += len(chunk)
                        if length > max_bytes:
                            raise BackendUnavailable("Backend response exceeds byte cap")
                        parts.append(chunk)
            body = b"".join(parts)
            self._validate_json_depth(body)
            data: Any = json.loads(body, parse_constant=self._deny_nonfinite)
            self._validate_numbers(data)
            if not isinstance(data, dict):
                raise BackendUnavailable("Backend envelope is not an object")
            return data
        except (
            httpx.HTTPError,
            TimeoutError,
            UnicodeDecodeError,
            ValueError,
            RecursionError,
        ) as exc:
            raise BackendUnavailable("Backend request or JSON parse failed") from exc

    @staticmethod
    def _deny_nonfinite(value: str) -> Any:
        raise ValueError("Non-finite JSON numbers are forbidden")

    @staticmethod
    def _validate_numbers(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("JSON numeric overflow is forbidden")
        if isinstance(value, dict):
            for child in value.values():
                SafeBackendTransport._validate_numbers(child)
        elif isinstance(value, list):
            for child in value:
                SafeBackendTransport._validate_numbers(child)

    @staticmethod
    def _validate_json_depth(body: bytes) -> None:
        # Scan structural bytes before decoding; braces inside JSON strings are data.
        # Bound matches domain MAX_JSON_DEPTH shared with knowledge contracts.
        depth = 0
        quoted = escaped = False
        for char in body:
            if quoted:
                if escaped:
                    escaped = False
                elif char == 92:
                    escaped = True
                elif char == 34:
                    quoted = False
            elif char == 34:
                quoted = True
            elif char in (91, 123):
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise BackendUnavailable("Backend JSON exceeds depth limit")
            elif char in (93, 125):
                depth -= 1
