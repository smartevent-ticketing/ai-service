import json

import pytest
import yaml
from fastapi.testclient import TestClient
from knowledge_helpers import configure, make_bundle

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.domain.knowledge import digest
from smartevent_ai.infrastructure.knowledge_config import ReviewedRagConfig
from smartevent_ai.infrastructure.knowledge_runtime import RuntimePolicyReader
from smartevent_ai.infrastructure.settings import Settings


def test_disabled_baseline_and_no_model_download(monkeypatch) -> None:
    monkeypatch.setenv("RAG_ENABLED", "true")
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        ready = client.get("/health/ready").json()
        assert ready["policy_retrieval"]["status"] == "disabled"
        assert ready["status"] == "degraded" and ready["business_tools_enabled"] == []
        answer = client.post("/api/v1/chat", json={"message": "Chính sách hoàn tiền"}).json()
        assert answer["grounding"] == "NO_LIVE_DATA" and answer["citations"] == []
        assert client.post("/api/v1/knowledge/upload", json={}).status_code == 404


def test_test_environment_integrates_real_chunk_store_and_citations(tmp_path) -> None:
    catalog, output, manifest, _ = make_bundle(tmp_path)
    config = configure(tmp_path, catalog, output, manifest)
    with TestClient(create_app(Settings(config_dir=config, app_env="test", _env_file=None))) as api:
        ready = api.get("/health/ready").json()
        assert ready["policy_retrieval"]["status"] == "ready"
        assert ready["status"] == "degraded" and ready["business_tools_enabled"] == []
        reply = api.post("/api/v1/chat", json={"message": "Chính sách hoàn tiền"}).json()
        assert reply["grounding"] == "APPROVED_CORPUS" and reply["citations"]
        assert "Ngoại lệ" in reply["answer"] and "STAFF_SECRET" not in reply["answer"]
        assert reply["tool_called"] is None
        assert (
            api.post("/api/v1/chat", json={"message": "Xem đơn hàng của tôi"}).json()["grounding"]
            == "NO_LIVE_DATA"
        )
        assert (
            api.post(
                "/api/v1/chat",
                json={"message": "Chính sách hoàn tiền", "audience": "staff_internal"},
            ).status_code
            == 422
        )
        data = json.loads(catalog.read_bytes())
        data["sources"][0]["metadata"]["status"] = "revoked"
        catalog.write_text(json.dumps(data), encoding="utf-8")
        # Tampered catalog fails its trust anchor; there is no cached old answer.
        reply = api.post("/api/v1/chat", json={"message": "Chính sách hoàn tiền"}).json()
        assert reply["citations"] == [] and reply["grounding"] == "NO_LIVE_DATA"
        assert api.get("/health/ready").json()["policy_retrieval"]["status"] == "unavailable"


@pytest.mark.parametrize("environment", ["development", "production"])
def test_test_only_fixture_cannot_be_served_in_normal_runtime(tmp_path, environment) -> None:
    catalog, output, manifest, _ = make_bundle(tmp_path)
    root = configure(tmp_path, catalog, output, manifest)
    with TestClient(
        create_app(Settings(config_dir=root, app_env=environment, _env_file=None))
    ) as api:
        assert api.get("/health/ready").json()["policy_retrieval"]["status"] == "unavailable"
        assert api.post("/api/v1/chat", json={"message": "hoàn tiền"}).json()["citations"] == []


@pytest.mark.asyncio
async def test_gate_revocation_bad_config_and_disabled_paths(tmp_path) -> None:
    catalog, output, manifest, _ = make_bundle(tmp_path)
    root = configure(tmp_path, catalog, output, manifest)
    reader = RuntimePolicyReader(ReviewedRagConfig(root), True)
    assert (await reader.answer("hoàn tiền")).citations
    gates_path = root / "implementation_gates.yaml"
    data = json.loads(catalog.read_bytes())
    for entry in data["sources"]:
        entry["metadata"]["status"] = "revoked"
    catalog.write_text(json.dumps(data), encoding="utf-8")
    config_data = yaml.safe_load((root / "rag.yaml").read_text())
    config_data["catalog_sha256"] = digest(catalog.read_bytes())
    (root / "rag.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")
    assert reader.status() == "unavailable"
    assert not (await reader.answer("hoàn tiền")).citations
    gates = yaml.safe_load(gates_path.read_text())
    gates["gates"]["RAG-READONLY"]["status"] = "BLOCKED"
    gates_path.write_text(yaml.safe_dump(gates), encoding="utf-8")
    assert reader.status() == "unavailable" and not (await reader.answer("hoàn tiền")).citations
    (root / "rag.yaml").write_text("enabled: true\nunknown: true", encoding="utf-8")
    assert reader.status() == "unavailable"
    (root / "rag.yaml").unlink()
    assert reader.status() == "disabled" and not (await reader.answer("hoàn tiền")).citations
    (root / "rag.yaml").write_text("x" * 33000, encoding="utf-8")
    assert reader.status() == "unavailable"
