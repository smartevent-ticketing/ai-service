"""ASGI startup must finish a model probe before accepting chat requests."""

import pytest
from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.domain.dialogue import Intent, Understanding
from smartevent_ai.domain.errors import ModelUnavailable
from smartevent_ai.infrastructure.settings import Settings


def test_lifespan_warms_same_provider_once_before_ready(monkeypatch) -> None:
    providers = []

    def warmup(provider):
        providers.append(provider)
        return Understanding(Intent.GREETING, mode="model")

    monkeypatch.setattr(PeftTransformerNLU, "warmup", warmup)
    app = create_app(Settings(nlu_backend="peft", nlu_preload=True, _env_file=None))
    assert not providers
    assert app.state.nlu_startup == "pending"
    with TestClient(app) as client:
        assert providers == [app.state.chat._nlu]
        body = client.get("/health/ready").json()
        assert body["nlu_startup"] == "ready"
        assert body["last_nlu_mode"] == "model"
        assert body["nlu_availability"] == "available"
        assert body["business_tools_enabled"] == []
    assert len(providers) == 1


def test_failed_warmup_aborts_startup(monkeypatch) -> None:
    def fail(_):
        raise ModelUnavailable("test startup failure")

    monkeypatch.setattr(PeftTransformerNLU, "warmup", fail)
    app = create_app(Settings(nlu_backend="peft", nlu_preload=True, _env_file=None))
    with pytest.raises(ModelUnavailable), TestClient(app):
        pytest.fail("Failed model must not finish startup")
    assert app.state.nlu_startup == "failed"


def test_lazy_model_cannot_report_ready_even_with_search_enabled(monkeypatch) -> None:
    app = create_app(Settings(nlu_backend="peft", nlu_preload=False, _env_file=None))
    monkeypatch.setattr(app.state.gateway, "available_names", lambda: ("search_events",))
    with TestClient(app) as client:
        body = client.get("/health/ready").json()
        assert body["status"] == "degraded"
        assert body["nlu_startup"] == "disabled"
        assert body["nlu_availability"] == "unverified"
