"""Exercise ASGI startup directly without sockets or GPU dependencies."""

import asyncio

import pytest

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.domain.dialogue import Intent, Understanding
from smartevent_ai.domain.errors import ModelUnavailable
from smartevent_ai.infrastructure.settings import Settings


def complete_inline(coroutine):
    """Drive a coroutine whose only external operation is stubbed below."""
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    pytest.fail("Unexpected asynchronous IO in the startup unit probe")


@pytest.mark.parametrize("mode", ["model", "fallback", "error"])
def test_startup_requires_model_probe_before_becoming_ready(monkeypatch, mode) -> None:
    calls = []

    async def thread_boundary(function):
        return function()

    def warmup(provider):
        calls.append(provider)
        if mode == "error":
            raise ModelUnavailable("Test model failed")
        return Understanding(Intent.GREETING, mode=mode)

    monkeypatch.setattr(asyncio, "to_thread", thread_boundary)
    monkeypatch.setattr(PeftTransformerNLU, "warmup", warmup)
    app = create_app(Settings(nlu_backend="peft", nlu_preload=True, _env_file=None))
    assert not calls
    assert app.state.nlu_startup == "pending"
    lifespan = app.router.lifespan_context(app)
    if mode != "model":
        with pytest.raises(ModelUnavailable):
            complete_inline(lifespan.__aenter__())
        assert app.state.nlu_startup == "failed"
        assert app.state.chat.last_nlu_mode == "unavailable"
    else:
        complete_inline(lifespan.__aenter__())
        assert app.state.nlu_startup == "ready"
        assert app.state.chat.last_nlu_mode == "model"
        complete_inline(lifespan.__aexit__(None, None, None))
    assert calls == [app.state.chat._nlu]
