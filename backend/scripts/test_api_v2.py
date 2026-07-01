"""Manual HTTP-level verification for app_v2.py (Phase 3).

Uses FastAPI's TestClient (real ASGI request/response cycle, not calling the
graph directly) to run through /chat, /session/{id}, /health, /ready, /delete.

Run:
    python -m scripts.test_api_v2
"""

import sys
import time
import uuid

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient

from app_v2 import app


def wait_until_ready(client: TestClient, timeout: int = 120) -> None:
    start = time.time()
    while time.time() - start < timeout:
        r = client.get("/ready")
        data = r.json()
        if data["ready"]:
            print(f"Ready after {time.time() - start:.1f}s")
            return
        if data["init_error"]:
            raise RuntimeError(f"Init failed: {data['init_error']}")
        time.sleep(1)
    raise TimeoutError("Server did not become ready in time")


def print_exchange(label: str, method: str, path: str, resp, body=None):
    print("-" * 90)
    print(f"[{label}] {method} {path}")
    if body is not None:
        print(f"  REQUEST BODY: {body}")
    print(f"  STATUS: {resp.status_code}")
    print(f"  RESPONSE: {resp.json()}")


def main():
    with TestClient(app) as client:
        r = client.get("/health")
        print_exchange("health (before ready)", "GET", "/health", r)
        assert r.status_code == 200

        wait_until_ready(client)

        session_id = f"test-{uuid.uuid4()}"

        # 1. Fresh session, sales-intent message
        body = {"session_id": session_id, "message": "show me laptops under 40000"}
        r = client.post("/chat", json=body)
        print_exchange("chat turn 1 (sales)", "POST", "/chat", r, body)
        assert r.status_code == 200
        data1 = r.json()
        assert data1["intent"] == "sales"
        assert data1["agent_used"] == "Sales Agent"
        assert isinstance(data1["retrieved_products"], list) and len(data1["retrieved_products"]) > 0

        # 2. Same session, follow-up — verify context persisted ACROSS separate HTTP calls
        body = {"session_id": session_id, "message": "how's the camera on this one?"}
        r = client.post("/chat", json=body)
        print_exchange("chat turn 2 (technical, same session)", "POST", "/chat", r, body)
        assert r.status_code == 200
        data2 = r.json()
        assert data2["intent"] == "technical"

        # 3. GET /session/{id} — confirm it reflects state built across the two HTTP calls above
        r = client.get(f"/session/{session_id}")
        print_exchange("get session (after 2 turns)", "GET", f"/session/{session_id}", r)
        assert r.status_code == 200
        session_data = r.json()
        assert session_data["exists"] is True
        assert session_data["selected_category"] == "Laptop"
        assert session_data["selected_product"] is not None
        assert session_data["message_count"] == 4  # 2 user + 2 assistant

        # 4. DELETE /session/{id}
        r = client.delete(f"/session/{session_id}")
        print_exchange("delete session", "DELETE", f"/session/{session_id}", r)
        assert r.status_code == 200
        assert r.json()["cleared"] is True

        # follow-up GET should show fresh/empty state
        r = client.get(f"/session/{session_id}")
        print_exchange("get session (after delete)", "GET", f"/session/{session_id}", r)
        assert r.status_code == 200
        session_data_after = r.json()
        assert session_data_after["exists"] is False
        assert session_data_after["message_count"] == 0

        # 5. Full booking flow through HTTP endpoints end to end
        booking_session = f"test-booking-{uuid.uuid4()}"
        body = {"session_id": booking_session, "message": "show me refrigerators under 25000"}
        r = client.post("/chat", json=body)
        print_exchange("booking turn 1 (browse)", "POST", "/chat", r, body)
        assert r.status_code == 200

        body = {"session_id": booking_session, "message": "book it"}
        r = client.post("/chat", json=body)
        print_exchange("booking turn 2 (select+book, missing details)", "POST", "/chat", r, body)
        assert r.status_code == 200
        assert r.json()["agent_used"] == "Booking Agent"

        body = {
            "session_id": booking_session,
            "message": "name: Rahul Sharma, address: 221B MG Road Mumbai, payment: UPI",
        }
        r = client.post("/chat", json=body)
        print_exchange("booking turn 3 (details -> pay -> confirm)", "POST", "/chat", r, body)
        assert r.status_code == 200

        r = client.get(f"/session/{booking_session}")
        print_exchange("get session (after booking)", "GET", f"/session/{booking_session}", r)
        booking_state = r.json()["booking_state"]
        assert booking_state["step"] == "confirmed"
        assert booking_state["order"]["order_id"]
        print(f"  [check] order confirmed: {booking_state['order']}")

        # 6. Malformed request — empty message should not crash the server
        body = {"session_id": "malformed-test", "message": ""}
        r = client.post("/chat", json=body)
        print_exchange("malformed request (empty message)", "POST", "/chat", r, body)
        assert r.status_code == 400

        body = {"session_id": "", "message": "hello"}
        r = client.post("/chat", json=body)
        print_exchange("malformed request (empty session_id)", "POST", "/chat", r, body)
        assert r.status_code == 400

        # missing field entirely -> 422 from pydantic validation
        r = client.post("/chat", json={"message": "hello"})
        print_exchange("malformed request (missing session_id field)", "POST", "/chat", r, {"message": "hello"})
        assert r.status_code == 422

        print("-" * 90)
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
