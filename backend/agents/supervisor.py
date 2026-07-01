import json
import re
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.state import AgentState

_VALID_INTENTS = {"sales", "technical", "booking", "clarify"}

_CATEGORY_KEYWORDS = {
    "Laptop": ["laptop", "laptops", "notebook", "computer"],
    "Mobile": ["phone", "phones", "mobile", "mobiles", "smartphone"],
    "TV": ["tv", "television", "screen"],
    "Refrigerator": ["fridge", "refrigerator", "refrigerators"],
    "Smart Watch": ["watch", "smartwatch", "smart watch"],
    "Washing Machine": ["washing machine", "washer", "washing"],
}

_SALES_KEYWORDS = ["price", "cost", "emi", "offer", "discount", "deal", "availability", "available", "exchange"]
_TECHNICAL_KEYWORDS = ["spec", "specs", "specification", "compare", "comparison", "vs", "feature", "camera", "battery", "pros", "cons", "processor", "ram"]
_BOOKING_KEYWORDS = ["buy", "book", "purchase", "confirm", "order", "checkout", "take it", "i'll take"]

_BUDGET_MAX_RE = re.compile(r"(?:under|below|less than|within|upto|up to)\s*(?:rs\.?|inr|₹)?\s*([\d,]+)", re.IGNORECASE)
_BUDGET_MIN_RE = re.compile(r"(?:above|over|more than)\s*(?:rs\.?|inr|₹)?\s*([\d,]+)", re.IGNORECASE)
_RATING_RE = re.compile(r"(?:rating|rated)\s*(?:above|over|at least|>=?)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

_SYSTEM_PROMPT = (
    "You are an intent classifier for a shopping assistant. Given the latest user "
    "message (and brief context), classify it into exactly one of: "
    "\"sales\" (pricing, EMI, bank offers, exchange offers, availability), "
    "\"technical\" (specs, feature explanations, comparisons, pros/cons), "
    "\"booking\" (user is ready to purchase/confirm an order), "
    "\"clarify\" (ambiguous — you cannot tell what the user wants without asking).\n"
    'Respond with raw JSON only, no markdown: {"intent": "sales|technical|booking|clarify"}'
)


def _keyword_classify(message: str) -> str:
    text = message.lower()
    if any(kw in text for kw in _BOOKING_KEYWORDS):
        return "booking"
    if any(kw in text for kw in _SALES_KEYWORDS):
        return "sales"
    if any(kw in text for kw in _TECHNICAL_KEYWORDS):
        return "technical"
    return "clarify"


def _llm_classify(llm, message: str, state: AgentState) -> Optional[str]:
    try:
        context_bits = []
        if state.get("selected_category"):
            context_bits.append(f"selected_category={state['selected_category']}")
        if state.get("selected_product"):
            context_bits.append(f"selected_product={state['selected_product'].get('product_name')}")
        context = " | ".join(context_bits) or "none"

        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=f"Context: {context}\nUser message: {message}"),
            ]
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        intent = parsed.get("intent")
        return intent if intent in _VALID_INTENTS else None
    except Exception:
        return None


def _extract_category(message: str) -> Optional[str]:
    text = message.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return None


def _extract_filters(message: str) -> dict:
    filters = {}
    max_match = _BUDGET_MAX_RE.search(message)
    if max_match:
        filters["budget_max"] = float(max_match.group(1).replace(",", ""))
    min_match = _BUDGET_MIN_RE.search(message)
    if min_match:
        filters["budget_min"] = float(min_match.group(1).replace(",", ""))
    rating_match = _RATING_RE.search(message)
    if rating_match:
        filters["min_rating"] = float(rating_match.group(1))
    return filters


def _maybe_select_product(state: AgentState, message: str) -> Optional[dict]:
    """Heuristic: if the user is moving to booking and hasn't picked a product yet,
    but there are retrieved products from a prior turn, select the first one.
    A real implementation would parse product name/ordinal references from the
    message; this is a simple fallback, flagged as a scope decision."""
    if state.get("selected_product"):
        return state["selected_product"]
    products = state.get("retrieved_products") or []
    if products:
        return products[0]
    return None


def make_supervisor_node(llm):
    def supervisor_node(state: AgentState) -> AgentState:
        # Second visit (after an agent ran and set _agent_responded): end the turn.
        if state.get("_agent_responded"):
            return state

        messages = state.get("messages", [])
        last_human = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
        )

        intent = _llm_classify(llm, last_human, state)
        used_fallback = False
        if intent is None:
            intent = _keyword_classify(last_human)
            used_fallback = True

        new_state = dict(state)
        new_state["intent"] = intent
        new_state["_used_keyword_fallback"] = used_fallback

        category = _extract_category(last_human)
        if category:
            new_state["selected_category"] = category

        extracted_filters = _extract_filters(last_human)
        if extracted_filters:
            merged_filters = dict(state.get("filters") or {})
            merged_filters.update(extracted_filters)
            new_state["filters"] = merged_filters

        if intent == "booking":
            selected = _maybe_select_product(new_state, last_human)
            if selected:
                new_state["selected_product"] = selected

        if intent == "clarify":
            clarify_msg = AIMessage(
                content=(
                    "I want to make sure I get this right — are you asking about "
                    "pricing/offers, specs/comparisons, or ready to book something?"
                )
            )
            new_state["messages"] = messages + [clarify_msg]
            new_state["_agent_responded"] = True

        return new_state

    return supervisor_node


def route_after_supervisor(state: AgentState) -> str:
    if state.get("_agent_responded"):
        return "end"
    intent = state.get("intent")
    if intent in ("sales", "technical", "booking"):
        return intent
    return "end"
