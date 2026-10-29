from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app


def test_liveness(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "alive"}


def test_not_fake_ready(client: TestClient) -> None:
    body = client.get("/health/ready").json()
    assert body["status"] == "degraded" and body["business_tools_enabled"] == []


def test_nlu_chat_no_unverified_business_data(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "Tìm 2 vé concert ở Hà Nội"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "SEARCH_EVENT"
    assert data["grounding"] == "NO_LIVE_DATA"
    assert data["state"]["quantity"] == 2
    assert data["state"]["city"] == "Hà Nội"
    assert data["state"]["search_query"] == "concert"
    assert "Chưa thể xác minh" in data["answer"]


def test_second_turn_stateless_merge(client: TestClient) -> None:
    r1 = client.post("/api/v1/chat", json={"message": "3 vé dưới 1 triệu tổng"}).json()
    r2 = client.post(
        "/api/v1/chat",
        json={
            "message": "Đổi thành 2 vé",
            "previous_state": r1["state"],
            "conversation_id": r1["conversation_id"],
        },
    ).json()
    assert r2["state"]["quantity"] == 2
    assert r2["state"]["budget_amount"] == 1_000_000
    assert r2["conversation_id"] == r1["conversation_id"]


def test_budget_scope_followup_resolves_without_losing_state(client: TestClient) -> None:
    r1 = client.post("/api/v1/chat", json={"message": "3 vé dưới 800 nghìn"}).json()
    assert "chưa lọc được" in r1["answer"]
    assert "mỗi vé hay tổng" not in r1["answer"]
    r2 = client.post(
        "/api/v1/chat",
        json={
            "message": "Tính tổng nhé",
            "previous_state": r1["state"],
            "conversation_id": r1["conversation_id"],
        },
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["state"]["budget_scope"] == "TOTAL"
    assert data["state"]["budget_amount"] == 800_000


def test_large_budget_never_becomes_server_error(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "3 vé dưới 2000 triệu tổng"})
    assert response.status_code == 200
    assert "ngoài phạm vi" in response.json()["answer"]


def test_user_mutation_request_only_guides(client: TestClient) -> None:
    result = client.post("/api/v1/chat", json={"message": "Giữ vé giúp tôi"}).json()
    assert result["intent"] == "BOOKING_GUIDANCE"
    assert "không giữ" in result["answer"]


def test_no_business_mutation_http_routes(client: TestClient) -> None:
    for endpoint in ("/api/v1/reservations", "/api/v1/orders", "/api/v1/payments/create-url"):
        assert client.post(endpoint, json={}).status_code == 404
    assert client.get("/api/v1/tools/search_events").status_code == 404


def test_rejects_unexpected_state_and_too_long_message(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/chat", json={"message": "hello", "previous_state": {"isAdmin": True}}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/chat", json={"message": "x" * 2001}).status_code == 422


def test_business_tool_gate_environment_override_ignored(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REGISTRY_PATH", str(tmp_path / "forged_tools.yaml"))
    monkeypatch.setenv("GATES_PATH", str(tmp_path / "forged_gates.yaml"))
    app = create_app()
    api = TestClient(app)
    assert api.get("/health/ready").json()["business_tools_enabled"] == []


def test_packaged_entrypoint_imports() -> None:
    from smartevent_ai.main import app

    assert app.title == "SmartEvent AI Read-only Service"


def test_whitespace_only_inputs_are_validation_errors_not_server_errors(
    client: TestClient,
) -> None:
    assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 422
    response = client.post(
        "/api/v1/chat",
        json={"message": "hello", "previous_state": {"city": "   "}},
    )
    assert response.status_code == 422
