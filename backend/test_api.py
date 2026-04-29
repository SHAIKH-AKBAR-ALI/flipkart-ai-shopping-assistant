import json
import sys
import requests

BASE_URL = "http://localhost:8000"
REQUIRED_KEYS = {"answer", "products", "follow_ups", "intent", "rag_trace"}


def check_health():
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    resp.raise_for_status()
    print(f"Health check: {resp.json()}")


def test_chat():
    payload = {
        "query": "best bluetooth headphones",
        "session_id": "test-session-1",
        "filters": {},
    }

    print(f"\nPOST /chat")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("-" * 60)

    resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=120)
    resp.raise_for_status()

    data = resp.json()

    print("Full response:")
    print(json.dumps(data, indent=2))
    print("-" * 60)

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        print(f"FAIL: Missing keys: {missing}")
        sys.exit(1)
    else:
        print(f"Key check PASSED. All required keys present: {REQUIRED_KEYS}")

    rag = data.get("rag_trace", {})
    print(f"\nRAG trace summary:")
    print(f"  query_variants:    {rag.get('query_variants', [])}")
    print(f"  docs_retrieved:    {rag.get('docs_retrieved', 'N/A')}")
    print(f"  docs_after_rerank: {rag.get('docs_after_rerank', 'N/A')}")
    print(f"  retrieval_time:    {rag.get('retrieval_time', 'N/A')}s")

    ragas = rag.get("ragas", {})
    if ragas:
        print(f"\nRAGAS scores:")
        for k, v in ragas.items():
            print(f"  {k}: {v}")

    print(f"\nIntent: {data.get('intent')}")
    print(f"Products returned: {len(data.get('products', []))}")
    print(f"Follow-ups: {data.get('follow_ups', [])}")


def test_clear_session():
    resp = requests.delete(f"{BASE_URL}/session/test-session-1", timeout=5)
    resp.raise_for_status()
    print(f"\nDELETE /session/test-session-1: {resp.json()}")


if __name__ == "__main__":
    print("=" * 60)
    print("Flipkart RAG API Test")
    print("=" * 60)

    print("\n[1] Health check")
    check_health()

    print("\n[2] Chat test")
    test_chat()

    print("\n[3] Clear session")
    test_clear_session()

    print("\n" + "=" * 60)
    print("All tests passed.")
    print("=" * 60)
