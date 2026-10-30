"""Minimal request tracing; never records messages, state, credentials or payloads."""

import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("smartevent_ai.requests")
_KNOWN_ROUTES = frozenset(("/health/live", "/health/ready", "/api/v1/chat"))


class RequestTelemetry:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = trace_id
        start = perf_counter()
        status = 500

        async def traced_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", trace_id.encode("ascii")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        finally:
            path = scope.get("path", "")
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "trace_id": trace_id,
                        "route": path if path in _KNOWN_ROUTES else "unmatched",
                        "status": status,
                        "latency_ms": round((perf_counter() - start) * 1000, 3),
                        "error_code": scope["state"].get("error_code"),
                        **scope["state"].get("chat_outcome", {}),
                    },
                    sort_keys=True,
                )
            )
