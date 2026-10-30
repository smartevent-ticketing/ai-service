import gc
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest

from smartevent_ai.adapters.outbound.sequential_peft import SequentialPeftPool
from smartevent_ai.adapters.outbound.peft_nlu import PeftTransformerNLU
from smartevent_ai.adapters.outbound.knowledge.policy_synthesizer import PeftPolicySynthesizer
from smartevent_ai.domain.dialogue import DialogueState
from smartevent_ai.domain.errors import ModelUnavailable
from smartevent_ai.infrastructure.bootstrap import build_chat
from smartevent_ai.infrastructure.settings import Settings


@pytest.fixture
def pool(monkeypatch):
    runtime = SequentialPeftPool()
    monkeypatch.setattr(runtime, "_release_memory", gc.collect)
    return runtime


def test_old_weights_are_unloaded_before_next_model_loads_and_same_role_is_reused(pool):
    actions = []
    pool.register("nlu", lambda: actions.append("unload_nlu"))
    pool.register("rag", lambda: actions.append("unload_rag"))
    for role in ("nlu", "nlu", "rag", "nlu"):
        pool.run(role, lambda r=role: actions.append("run_" + r))
    assert actions == ["run_nlu", "run_nlu", "unload_nlu", "run_rag", "unload_rag", "run_nlu"]
    assert pool.status()["switches"] == 2
    pool.close()
    with pytest.raises(ModelUnavailable):
        pool.run("nlu", lambda: None)


def test_rag_cannot_evict_nlu_while_nlu_is_generating(pool):
    entered, finish, rag_started = threading.Event(), threading.Event(), threading.Event()
    unload = []
    pool.register("nlu", lambda: unload.append("nlu"))
    pool.register("rag", lambda: unload.append("rag"))

    def nlu():
        entered.set()
        assert finish.wait(3)
        assert not unload

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(pool.run, "nlu", nlu)
        assert entered.wait(3)
        second = executor.submit(pool.run, "rag", rag_started.set)
        try:
            assert not rag_started.wait(0.05)
            assert pool.status()["active_model"] == "nlu"
        finally:
            finish.set()
        first.result(timeout=3)
        second.result(timeout=3)
    assert rag_started.is_set() and unload == ["nlu"]


def test_failed_loading_drops_tensors_retained_by_exception_frames(pool):
    references = []

    class TensorStandIn:
        pass

    def fail():
        temporary_weights = TensorStandIn()
        references.append(weakref.ref(temporary_weights))
        raise RuntimeError("Simulated out of GPU memory")

    pool.register("rag", lambda: None)
    with pytest.raises(RuntimeError):
        pool.run("rag", fail)
    assert references[0]() is None
    assert pool.status()["active_model"] is None
    assert pool.run("rag", lambda: "recovered") == "recovered"


def test_both_real_adapter_entrypoints_share_eviction_and_release_references(pool, monkeypatch):
    nlu = PeftTransformerNLU(model_pool=pool)
    rag = PeftPolicySynthesizer(model_pool=pool)

    class Weights:
        pass

    def nlu_generate(*_):
        assert rag._model is None
        nlu._model = Weights()
        nlu._tokenizer = object()
        return '{"primary_intent":"SEARCH_EVENT","entities":{"city":"Hà Nội","quantity":2}}'

    def rag_generate(*_):
        assert nlu._model is None and nlu._tokenizer is None
        rag._model = Weights()
        rag._tokenizer = object()
        return "Demo answer"

    monkeypatch.setattr(nlu, "_generate_once", nlu_generate)
    monkeypatch.setattr(rag, "_synthesize_once", rag_generate)
    assert nlu.parse("test", DialogueState()).mode == "model"
    old_nlu = weakref.ref(nlu._model)
    assert rag.synthesize("query", "context") == "Demo answer"
    assert old_nlu() is None and rag.last_mode == "model"
    old_rag = weakref.ref(rag._model)
    assert nlu.parse("test", DialogueState()).mode == "model"
    assert old_rag() is None
    pool.close()
    assert nlu._model is None and rag._model is None


def test_failed_rag_falls_back_only_after_releasing_partial_model(pool, monkeypatch):
    rag = PeftPolicySynthesizer(model_pool=pool)

    def broken(*_):
        rag._model = object()
        raise RuntimeError("Test loading failure")

    monkeypatch.setattr(rag, "_synthesize_once", broken)
    assert rag.synthesize("query", "evidence") == "evidence"
    assert rag.last_mode == "fallback" and rag._model is None
    assert pool.status()["active_model"] is None


def test_demo_bootstrap_shares_one_pool_and_preserves_closed_business_gates():
    settings = Settings(
        nlu_backend="peft",
        rag_backend="peft",
        peft_sequential=True,
        nlu_timeout_seconds=180,
        rag_generation_timeout_seconds=180,
        _env_file=None,
    )
    chat, gateway = build_chat(settings)
    assert chat._nlu._model_pool is chat._policies._synthesizer._model_pool
    assert chat._nlu._model_pool is not None
    assert chat._nlu_timeout_seconds == 180
    assert chat._policies._generation_timeout_seconds == 180
    assert gateway.available_names() == ()
    assert chat.policy_status() == "disabled"


@pytest.mark.parametrize(
    "override",
    [
        {"nlu_backend": "rule"},
        {"rag_backend": "extractive"},
        {"policy_backend": "http"},
        {"rag_load_4bit": False},
        {"nlu_load_4bit": False},
    ],
)
def test_invalid_sequential_configuration_is_rejected(override):
    values = dict(nlu_backend="peft", rag_backend="peft", peft_sequential=True)
    values.update(override)
    with pytest.raises(ValueError):
        Settings(**values, _env_file=None)
