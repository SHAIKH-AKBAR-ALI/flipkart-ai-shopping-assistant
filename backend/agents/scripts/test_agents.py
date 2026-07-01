"""Manual verification script for the Supervisor + multi-agent LangGraph (Phase 2).

Runs 4 real multi-turn conversations through the compiled graph and prints
actual output at each turn: user message, classified intent, which agent
handled it, and the response.

Run:
    python -m agents.scripts.test_agents
"""

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage

from agents.graph import build_graph
from agents.state import new_state
from rag.retriever import HybridRetriever

_INTENT_TO_AGENT = {
    "sales": "Sales Agent",
    "technical": "Technical Agent",
    "booking": "Booking Agent",
    "clarify": "Supervisor (clarify)",
}


def run_turn(app, state, user_message: str):
    state = dict(state)
    state["messages"] = state["messages"] + [HumanMessage(content=user_message)]
    state["_agent_responded"] = False
    result = app.invoke(state)

    intent = result.get("intent")
    handler = _INTENT_TO_AGENT.get(intent, "?")
    last_ai = result["messages"][-1].content

    print(f"USER: {user_message}")
    print(f"  intent: {intent}  |  handled_by: {handler}")
    print(f"  selected_category: {result.get('selected_category')}  |  filters: {result.get('filters')}")
    if result.get("selected_product"):
        print(f"  selected_product: {result['selected_product'].get('product_name')}")
    print(f"  RESPONSE: {last_ai}")
    print()
    return result


def conversation_1_stays_in_sales(app):
    print("=" * 90)
    print("CONVERSATION 1 — stays in Sales the whole time")
    print("=" * 90)
    state = new_state()
    state = run_turn(app, state, "show me laptops under 40000")
    state = run_turn(app, state, "what EMI options do I have")
    return state


def conversation_2_intent_shift(app):
    print("=" * 90)
    print("CONVERSATION 2 — intent shift mid-way (Sales -> Technical), selected_product carries over")
    print("=" * 90)
    state = new_state()
    state = run_turn(app, state, "what's the price of laptops under 40000")
    product_after_sales = state.get("selected_product", {}).get("product_name")
    state = run_turn(app, state, "how's the camera on this one?")
    product_after_technical = state.get("selected_product", {}).get("product_name")
    print(f"  [check] selected_product before shift: {product_after_sales!r}")
    print(f"  [check] selected_product after shift:  {product_after_technical!r}")
    print(f"  [check] carried over correctly: {product_after_sales == product_after_technical}")
    print()
    return state


def conversation_3_full_booking(app):
    print("=" * 90)
    print("CONVERSATION 3 — full booking flow (browse -> select -> confirm -> payment + order)")
    print("=" * 90)
    state = new_state()
    state = run_turn(app, state, "show me refrigerators under 25000")
    state = run_turn(app, state, "book it")
    state = run_turn(
        app,
        state,
        "name: Rahul Sharma, address: 221B MG Road Mumbai, payment: UPI",
    )
    booking_state = state.get("booking_state") or {}
    print(f"  [check] booking step: {booking_state.get('step')}")
    print(f"  [check] payment_result: {booking_state.get('payment_result')}")
    print(f"  [check] order: {booking_state.get('order')}")
    print()
    return state


def conversation_4_ambiguous_clarify(app):
    print("=" * 90)
    print("CONVERSATION 4 — ambiguous first message triggers 'clarify'")
    print("=" * 90)
    state = new_state()
    state = run_turn(app, state, "hmm okay")
    return state


def main():
    print("Building retriever + compiling graph (once)...")
    retriever = HybridRetriever()
    app = build_graph(retriever=retriever)
    print("Graph compiled.\n")

    conversation_1_stays_in_sales(app)
    conversation_2_intent_shift(app)
    conversation_3_full_booking(app)
    conversation_4_ambiguous_clarify(app)


if __name__ == "__main__":
    main()
