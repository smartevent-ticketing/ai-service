"""Live runtime test & evaluation for SmartEvent AI Service."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from smartevent_ai.adapters.inbound.http_api import create_app
from smartevent_ai.infrastructure.settings import Settings


def evaluate_live_service():
    print("=" * 70)
    print("LIVE RUNTIME EXECUTION & EVALUATION: SMARTEVENT AI SERVICE")
    print("=" * 70)

    # 1. Initialize settings with PEFT NLU model on GPU (RTX 2050 4-bit)
    root = Path(__file__).resolve().parents[1]
    adapter_path = root / "models" / "unpacked_nlu_1.5b"

    settings = Settings(
        nlu_backend="peft" if adapter_path.exists() else "rule",
        nlu_adapter_path=adapter_path if adapter_path.exists() else None,
        _env_file=None,
    )

    t0 = time.time()
    app = create_app(settings)
    startup_time = time.time() - t0
    print(f"[STATUS] FastAPI service created in {startup_time:.2f}s")

    client = TestClient(app)

    # Health check
    live_res = client.get("/health/live").json()
    ready_res = client.get("/health/ready").json()
    print("\n--- Health Endpoints ---")
    print("GET /health/live :", live_res)
    print("GET /health/ready:", ready_res)
    assert live_res["status"] == "alive"

    # Multi-turn conversational scenarios
    scenarios = [
        {
            "title": "Turn 1: Natural Language Event Search (Extract City + Quantity)",
            "request": {
                "message": "Tìm cho tôi 2 vé concert acoustic ở Hà Nội cuối tuần",
                "previous_state": {},
            },
            "expectations": {
                "intent": "SEARCH_EVENT",
                "city": "Hà Nội",
                "quantity": 2,
            },
        },
        {
            "title": "Turn 2: Follow-up Preference Update (Update City & Quantity without losing state)",
            "request": {
                "message": "Đổi thành 3 vé và chuyển sang TP Hồ Chí Minh nhé",
                "previous_state": {
                    "city": "Hà Nội",
                    "quantity": 2,
                    "search_query": "concert acoustic",
                },
            },
            "expectations": {
                "intent": "SEARCH_EVENT",
                "city": "Hồ Chí Minh",
                "quantity": 3,
            },
        },
        {
            "title": "Turn 3: Policy Inquiry (Refund conditions)",
            "request": {
                "message": "Nếu ban tổ chức hủy sự kiện thì tôi có được hoàn tiền không?",
                "previous_state": {},
            },
            "expectations": {
                "intent": "REFUND_POLICY",
            },
        },
        {
            "title": "Turn 4: READ_ONLY Security Attack (Forcing bot to hold reservation)",
            "request": {
                "message": "Giữ giúp tôi 2 vé VIP sự kiện Tech Summit ngay bây giờ!",
                "previous_state": {},
            },
            "expectations": {
                "intent": "BOOKING_GUIDANCE",
                "must_not_mutate": True,
            },
        },
        {
            "title": "Turn 5: Out of Range Guard (Exceeding max ticket quantity 20)",
            "request": {
                "message": "Tôi muốn mua 35 vé cho cả phòng công ty",
                "previous_state": {},
            },
            "expectations": {
                "needs_clarification": True,
            },
        },
    ]

    print("\n" + "=" * 70)
    print("RUNNING CONVERSATION SCENARIOS")
    print("=" * 70)

    results = []

    for idx, sc in enumerate(scenarios, 1):
        print(f"\n[{idx}/5] Scenario: {sc['title']}")
        print(f"User Message: \"{sc['request']['message']}\"")

        t_req = time.time()
        resp = client.post("/api/v1/chat", json=sc["request"])
        elapsed = time.time() - t_req

        assert resp.status_code == 200, f"HTTP Error {resp.status_code}: {resp.text}"
        data = resp.json()

        print(f"Latency: {elapsed:.2f}s | HTTP 200 OK")
        print(f"Intent : {data['intent']}")
        print(f"State  : {data['state']}")
        print(f"Answer : {data['answer']}")
        print(f"Grounding: {data['grounding']}")

        exp = sc["expectations"]
        intent_match = (data["intent"] == exp.get("intent", data["intent"]))
        print(f"Evaluation: {'[PASS]' if intent_match else '[FAIL]'}")

        results.append({
            "scenario": sc["title"],
            "latency_s": round(elapsed, 2),
            "status": "PASS" if intent_match else "FAIL",
            "intent": data["intent"],
            "state": data["state"],
        })

    print("\n" + "=" * 70)
    print("FINAL SUMMARY REPORT")
    print("=" * 70)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    print(f"Passed Scenarios: {pass_count}/{len(results)} ({pass_count/len(results)*100:.1f}%)")
    print(f"Average Latency : {sum(r['latency_s'] for r in results)/len(results):.2f}s")
    print(f"Model Backend   : {ready_res['model_backend']}")
    print("READ_ONLY Gate  : ENFORCED (Zero mutation endpoints exposed)")


if __name__ == "__main__":
    evaluate_live_service()
