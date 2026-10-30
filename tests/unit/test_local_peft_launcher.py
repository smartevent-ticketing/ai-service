import importlib.util
from pathlib import Path

import httpx
import pytest


def launcher():
    path = Path(__file__).resolve().parents[2] / "scripts/local/run_peft.py"
    spec = importlib.util.spec_from_file_location("local_peft_launcher", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure", [None, "cold", "fallback", "disabled", "upstream"])
def test_http_probe_requires_warmed_model_and_real_search_outcome(monkeypatch, capsys, failure):
    module = launcher()
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/health/ready":
            return httpx.Response(
                200,
                json={
                    "model_backend": "peft",
                    "nlu_startup": "pending" if failure == "cold" else "ready",
                    "business_tools_enabled": ["search_events"],
                    "business_tool_capabilities": {"search_events": {"date_price_filters": True}},
                },
            )
        return httpx.Response(
            503 if failure == "upstream" else 200,
            json={
                "intent": "SEARCH_EVENT",
                "mode": "fallback" if failure == "fallback" else "model",
                "tool_called": None if failure == "disabled" else "search_events",
                "grounding": "BACKEND_READ",
                "status": "EMPTY",
                "events": [],
            },
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler))
    )
    if failure:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            module.verify_api(8001, "Test search")
    else:
        module.verify_api(8001, "Test search")
        assert "MODEL_BACKEND_HTTP_OK" in capsys.readouterr().out
    assert calls == [("GET", "/health/ready")] + (
        [] if failure == "cold" else [("POST", "/api/v1/chat")]
    )
