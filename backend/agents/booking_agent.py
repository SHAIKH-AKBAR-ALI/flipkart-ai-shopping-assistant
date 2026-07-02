import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from agents.state import AgentState
from rag.price_lookup import lookup_inr_price

_REQUIRED_FIELDS = ["name", "address", "phone", "payment_method"]

_ORDINAL_WORDS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
}

# Accepts "name: X", "address: Y", "phone: Z", "payment: Z" / "payment method: Z"
# (comma or newline separated), case-insensitive. Deterministic parsing only — no LLM.
_FIELD_RE = re.compile(
    r"(name|address|phone|payment(?:\s*method)?)\s*[:=]\s*([^,\n]+)", re.IGNORECASE
)

# Bare phone number fallback (no "phone:" label), e.g. "9876543210",
# "+91-9876543210", "91-9876543210". Captures the 10-digit subscriber number.
_BARE_PHONE_RE = re.compile(r"(?:\+?91[-\s]?)?(\d{10})\b")


def _extract_details(message: str) -> Dict[str, str]:
    details = {}
    for match in _FIELD_RE.finditer(message):
        key = match.group(1).lower().replace(" ", "")
        value = match.group(2).strip()
        if key == "payment" or key == "paymentmethod":
            details["payment_method"] = value
        else:
            details[key] = value

    if not details.get("phone"):
        m = _BARE_PHONE_RE.search(message)
        if m:
            details["phone"] = m.group(1)

    return details


def _missing_fields(details: Dict[str, str]) -> list:
    return [f for f in _REQUIRED_FIELDS if not details.get(f)]


def _filter_by_mentioned_brand(products: list, text: str) -> list:
    """Narrow candidates to a single mentioned brand, if the message names one.
    Doesn't resolve ambiguity by itself — "motorola" still leaves several
    Motorola products in play, which is exactly the case that needs disambiguation."""
    text_l = text.lower()
    brands = {(p.get("brand") or "").lower() for p in products if p.get("brand")}
    mentioned = [b for b in brands if b and b in text_l]
    if len(mentioned) == 1:
        return [p for p in products if (p.get("brand") or "").lower() == mentioned[0]]
    return products


def _resolve_by_name(products: list, text: str) -> Optional[Dict[str, Any]]:
    """Select a product when its full name appears verbatim in the user's
    message. When several product names match (one being a substring of the
    text alongside a longer, more specific one), the longest — i.e. most
    specific — name wins. Returns None if nothing matches."""
    tl = text.lower()
    matches = [p for p in products if (p.get("product_name") or "").lower() in tl]
    if not matches:
        return None
    matches.sort(key=lambda p: len(p.get("product_name") or ""), reverse=True)
    return matches[0]


def _resolve_candidate(candidates: list, text: str) -> Optional[Dict[str, Any]]:
    """Resolve a user reply to one of the disambiguation candidates: by list
    number, ordinal word ("the second one"), or a uniquely-matching name substring."""
    text_l = text.lower().strip()

    m = re.match(r"^\D*(\d+)\b", text_l)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]

    for word, num in _ORDINAL_WORDS.items():
        if word in text_l:
            idx = num - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]

    name_matches = [c for c in candidates if (c.get("product_name") or "").lower() in text_l]
    if len(name_matches) == 1:
        return name_matches[0]

    return None


def _format_candidates(candidates: list) -> str:
    lines = ["I found a few matching products — which one do you mean?"]
    for i, p in enumerate(candidates, start=1):
        lines.append(f"{i}. {p.get('product_name')} — Rs.{p.get('price')}")
    lines.append("Reply with the number or the product name.")
    return "\n".join(lines)


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


def _is_bookable(product: Optional[Dict[str, Any]]) -> bool:
    """A product can only be ordered if it has a real, positive price. Live
    web-fallback results (web_source=True) carry no Indian pricing (0.0), so
    they can be shown/compared but not booked/paid for."""
    if not product:
        return False
    price = product.get("price")
    return price is not None and price > 0


_PAYMENT_CONFIRMED_TRIGGERS = {"payment_confirmed", "payment confirmed", "payment success", "payment_success"}
_PAYMENT_FAILED_TRIGGERS = {"payment_failed", "payment failed"}


def _create_order(selected_product: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
    return {
        "order_id": str(uuid.uuid4()),
        "product_name": selected_product.get("product_name"),
        "price": selected_product.get("price"),
        "price_source": selected_product.get("price_source", "catalog"),
        "transaction_id": transaction_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _phrase_confirmation(llm, order: Dict[str, Any]) -> str:
    if llm is None:
        return (
            f"Done — {order['product_name']} is officially yours. Order ID "
            f"{order['order_id']}, Rs.{order['price']}. Nicely chosen; we'll take it "
            f"from here."
        )
    try:
        from langchain_core.messages import HumanMessage as _HM
        from langchain_core.messages import SystemMessage as _SM

        response = llm.invoke(
            [
                _SM(content=(
                    "You're the Booking desk wrapping up a purchase. Write a short, "
                    "warm order-confirmation message using ONLY the order details "
                    "given — order id, product, price (Indian Rupees). One or two "
                    "sentences, genuinely pleased for them, a light touch of humor is "
                    "fine (think 'nicely done' not a stand-up routine). Do not invent "
                    "any detail, discount, or delivery date that isn't in the data."
                )),
                _HM(content=str(order)),
            ]
        )
        return response.content
    except Exception:
        return (
            f"Done — {order['product_name']} is officially yours. Order ID "
            f"{order['order_id']}, Rs.{order['price']}. Nicely chosen; we'll take it "
            f"from here."
        )


def make_booking_agent_node(llm=None):
    def booking_agent_node(state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        last_human = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
        )
        selected_product = state.get("selected_product")
        booking_state = state.get("booking_state") or {}

        new_state = dict(state)

        # Step 0: disambiguate which product, if not already picked and more
        # than one candidate is in play. Runs before details collection.
        if not selected_product:
            retrieved_products = state.get("retrieved_products") or []

            if booking_state.get("step") == "selecting_product":
                candidates = booking_state.get("candidates", [])
                resolved = _resolve_candidate(candidates, last_human)
                if resolved:
                    selected_product = resolved
                    new_state["selected_product"] = resolved
                    booking_state = {"step": "collecting_details", "details": {}}
                else:
                    reply = "I couldn't tell which one you meant.\n" + _format_candidates(candidates)
                    new_state["booking_state"] = booking_state
                    new_state["messages"] = messages + [AIMessage(content=reply)]
                    new_state["_agent_responded"] = True
                    new_state["_last_response"] = {"message": reply, "booking_state": booking_state}
                    return new_state
            else:
                if not retrieved_products:
                    reply = "I don't have a product selected yet — please pick one before booking."
                    new_state["messages"] = messages + [AIMessage(content=reply)]
                    new_state["_agent_responded"] = True
                    new_state["_last_response"] = {"message": reply, "booking_state": None}
                    return new_state

                # If the user already named a specific product (its full name
                # appears in the message, e.g. "book Godrej 200 L Direct Cool
                # ..."), select it directly — don't fall back to brand-only
                # disambiguation, which would needlessly re-ask when several
                # products share a brand.
                named = _resolve_by_name(retrieved_products, last_human)
                candidates = [named] if named else _filter_by_mentioned_brand(retrieved_products, last_human)
                if len(candidates) == 1:
                    selected_product = candidates[0]
                    new_state["selected_product"] = selected_product
                    booking_state = {"step": "collecting_details", "details": {}}
                else:
                    reply = _format_candidates(candidates)
                    booking_state = {"step": "selecting_product", "candidates": candidates, "details": {}}
                    new_state["booking_state"] = booking_state
                    new_state["messages"] = messages + [AIMessage(content=reply)]
                    new_state["_agent_responded"] = True
                    new_state["_last_response"] = {"message": reply, "booking_state": booking_state}
                    return new_state

        # Live-data (web_source) products have no verified price (0.0) — they
        # come from the external fallback API, not the catalog. Rather than
        # refuse outright, fetch an ESTIMATED INR price off the open web
        # (Tavily) and, if found, stamp it onto the product and go straight into
        # collecting details — the estimate disclaimer rides along on the first
        # form prompt, and the payment page later shows the exact amount the
        # user must approve, so no separate yes/no confirm turn is needed. If no
        # reliable price is found, refuse. Only runs when starting a booking —
        # never mid-payment (a product in processing can't be a web product, it
        # would never have passed validation).
        if (
            selected_product
            and not _is_bookable(selected_product)
            and booking_state.get("step") not in ("processing_payment", "creating_order", "confirmed")
        ):
            name = selected_product.get("product_name", "That product")
            est = lookup_inr_price(name, selected_product.get("brand", ""), llm)
            if est and est.get("price"):
                price = est["price"]
                confidence = est.get("confidence", "low")
                # Stamp the estimate onto the product so it becomes bookable, and
                # record price_source for auditability on the order.
                selected_product = dict(selected_product)
                selected_product["price"] = price
                selected_product["price_source"] = "web_estimate"
                new_state["selected_product"] = selected_product
                qualifier = "" if confidence == "high" else " (rough estimate)"
                booking_state = {
                    "step": "collecting_details",
                    "details": {},
                    "web_price_note": (
                        f"Note: “{name}” isn't in our catalog — I'm using an "
                        f"estimated web price of Rs.{price}{qualifier}, which isn't "
                        f"Flipkart-verified and may differ from the final amount.\n\n"
                    ),
                }
                # fall through into the collecting_details flow below

            else:
                reply = (
                    f"“{name}” is live web data and I couldn't find a reliable price "
                    "for it, so it can't be booked here. I can book any product from "
                    "our catalog — search within a budget and pick one to continue."
                )
                new_state["selected_product"] = None
                new_state["booking_state"] = None
                new_state["messages"] = messages + [AIMessage(content=reply)]
                new_state["_agent_responded"] = True
                new_state["_last_response"] = {"message": reply, "booking_state": None}
                return new_state

        booking_state = booking_state or {"step": "collecting_details", "details": {}}
        booking_state = dict(booking_state)
        booking_state["details"] = dict(booking_state.get("details", {}))

        # Step 1: collect details (deterministic parsing, no LLM decision-making)
        if booking_state["step"] == "collecting_details":
            booking_state["details"].update(_extract_details(last_human))
            missing = _missing_fields(booking_state["details"])
            if missing:
                # Show the web-estimate disclaimer once, on the first form prompt.
                note = booking_state.pop("web_price_note", "")
                reply = (
                    note +
                    "To confirm your booking I still need: " + ", ".join(missing) +
                    ". Please provide them (e.g. \"name: Rahul Sharma, address: 221B MG Road Mumbai, "
                    "phone: 9876543210, payment: UPI\")."
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

        # Step 3: process payment — waits for the frontend's math-challenge
        # page to signal success/failure via a "payment_confirmed" /
        # "payment_failed" message. No auto-mock success here anymore.
        if booking_state["step"] == "processing_payment":
            trigger = last_human.strip().lower()
            if trigger in _PAYMENT_CONFIRMED_TRIGGERS:
                booking_state["step"] = "creating_order"
            elif trigger in _PAYMENT_FAILED_TRIGGERS:
                booking_state["details"].pop("payment_method", None)
                booking_state["step"] = "collecting_details"
                reply = "Payment failed. Please try again."
                new_state["booking_state"] = booking_state
                new_state["messages"] = messages + [AIMessage(content=reply)]
                new_state["_agent_responded"] = True
                new_state["_last_response"] = {"message": reply, "booking_state": booking_state}
                return new_state
            else:
                reply = "Please complete the payment verification to continue."
                new_state["booking_state"] = booking_state
                new_state["messages"] = messages + [AIMessage(content=reply)]
                new_state["_agent_responded"] = True
                new_state["_last_response"] = {"message": reply, "booking_state": booking_state}
                return new_state

        # Step 4: create order
        if booking_state["step"] == "creating_order":
            order = _create_order(selected_product, str(uuid.uuid4()))
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
