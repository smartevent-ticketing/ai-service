"""Application entrypoint: ``uvicorn smartevent_ai.main:app``."""

from smartevent_ai.adapters.inbound.http_api import app, create_app

__all__ = ["app", "create_app"]
