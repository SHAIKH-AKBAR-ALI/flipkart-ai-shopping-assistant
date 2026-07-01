import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from agents.state import AgentState

_REQUIRED_FIELDS = ["name", "address", "payment_method"]

# Accepts "name: X", "address: Y", "payment: Z" / "payment method: Z" (comma or
# newline separated), case-insensitive. Deterministic parsing only — no LLM.
_FIELD_RE = re.compile(
    r"(name|address|payment(?:\s*method)?)\s*[:=]\s*([^,\n]+)", re.IGNORECASE
)


def _extract_details(message: str) -> Dict[str, str]:
    details = {}
    for match in _FIELD_RE.finditer(message):
        key = match.group(1).lower().replace(" ", "")
        value = match.group(2).strip()
        if key == "payment" or key == "paymentmethod":
            details["payment_method"] = value
        else:
            details[key] = value
    return details


def _missing_fields(details: Dict[str, str]) -> list:
    return [f for f in _REQUIRED_FIELDS if not details.get(f)]


def _validate_order(selected_product: Optional[Dict[str, Any]]) -> Optional[str]:
    """Returns an error message if invalid, else None."""
    if not selected_product:
        return "No product selected."
    price = selected_product.get("price")
    if price is None or price <= 0:
        return f"Invalid price for selected product: {price!r}."
    if not selected_product.get("product_name"):
        return "Selected product is missing a name."
    return None


def _mock_payment_gateway(details: Dict[str, str]) -> Dict[str, Any]:
    """Mocked payment step — isolated so a real provider can replace this
    function's body later without touching steps 1/2/4/5's structure."""
    time.sleep(0.05)  # simulate network latency
    method = (details.get("payment_method") or "").lower()
    success = "decline" not in method and "fail" not in method
    return {
        "success": success,
        "transaction_id": str(uuid.uuid4()) if success else None,
        "reason": None if success else "Payment declined by mock gateway.",
    }


def _create_order(selected_product: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
    return {
        "order_id": str(uuid.uuid4()),
        "product_name": selected_product.get("product_name"),
        "price": selected_product.get("price"),
        "transaction_id": transaction_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _phrase_confirmation(llm, order: Dict[str, Any]) -> str:
    if llm is None:
        return (
            f"Order confirmed! {order['product_name']} — Order ID {order['order_id']}, "
            f"Price Rs.{order['price']}. Thank you for shopping with us."
        )
    try:
        from langchain_core.messages import HumanMessage as _HM
        from langchain_core.messages import SystemMessage as _SM

        response = llm.invoke(
            [
                _SM(content="Phrase a short, friendly order confirmation message using the given order details. Do not invent details."),
                _HM(content=str(order)),
            ]
        )
        return response.content
    except Exception:
        return (
            f"Order confirmed! {order['product_name']} — Order ID {order['order_id']}, "
            f"Price Rs.{order['price']}. Thank you for shopping with us."
        )


def make_booking_agent_node(llm=None):
    def booking_agent_node(state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        last_human = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
        )
        selected_product = state.get("selected_product")

        new_state = dict(state)

        if not selected_product:
            reply = "I don't have a product selected yet — please pick one before booking."
            new_state["messages"] = messages + [AIMessage(content=reply)]
            new_state["_agent_responded"] = True
            new_state["_last_response"] = {"message": reply, "booking_state": None}
            return new_state

        booking_state = state.get("booking_state") or {"step": "collecting_details", "details": {}}
        booking_state = dict(booking_state)
        booking_state["details"] = dict(booking_state.get("details", {}))

        # Step 1: collect details (deterministic parsing, no LLM decision-making)
        if booking_state["step"] == "collecting_details":
            booking_state["details"].update(_extract_details(last_human))
            missing = _missing_fields(booking_state["details"])
            if missing:
                reply = (
                    "To confirm your booking I still need: " + ", ".join(missing) +
                    ". Please provide them (e.g. \"name: Rahul Sharma, address: 221B MG Road Mumbai, payment: UPI\")."
                )
                booking_state["step"] = "collecting_details"
                new_state["booking_state"] = booking_state
                new_state["messages"] = messages + [AIMessage(content=reply)]
                new_state["_agent_responded"] = True
                new_state["_last_response"] = {"message": reply, "booking_state": booking_state}
                return new_state
            booking_state["step"] = "validating"

        # Step 2: validate order details
        if booking_state["step"] == "validating":
            error = _validate_order(selected_product)
            if error:
                booking_state["step"] = "failed"
                booking_state["error"] = error
            else:
                booking_state["step"] = "processing_payment"

        # Step 3: process payment (mocked, isolated function)
        if booking_state["step"] == "processing_payment":
            payment_result = _mock_payment_gateway(booking_state["details"])
            booking_state["payment_result"] = payment_result
            if payment_result["success"]:
                booking_state["step"] = "creating_order"
            else:
                booking_state["step"] = "failed"
                booking_state["error"] = payment_result["reason"]

        # Step 4: create order
        if booking_state["step"] == "creating_order":
            order = _create_order(selected_product, booking_state["payment_result"]["transaction_id"])
            booking_state["order"] = order
            booking_state["step"] = "confirmed"

        # Step 5: confirm
        if booking_state["step"] == "confirmed":
            reply = _phrase_confirmation(llm, booking_state["order"])
        else:  # failed
            reply = f"Booking failed: {booking_state.get('error', 'unknown error')}"

        new_state["booking_state"] = booking_state
        new_state["messages"] = messages + [AIMessage(content=reply)]
        new_state["_agent_responded"] = True
        new_state["_last_response"] = {"message": reply, "booking_state": booking_state}
        return new_state

    return booking_agent_node
