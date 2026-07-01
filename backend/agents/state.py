from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: List[Any]  # conversation history (BaseMessage list)
    intent: Optional[str]  # "sales" | "technical" | "booking" | "clarify"
    selected_category: Optional[str]
    selected_product: Optional[Dict[str, Any]]
    filters: Dict[str, Any]  # budget_max, budget_min, min_rating
    retrieved_products: List[Dict[str, Any]]
    session_history: List[Dict[str, str]]
    booking_state: Optional[Dict[str, Any]]
    # Internal bookkeeping: set by a sub-agent once it has produced this
    # turn's response, so the Supervisor's second visit (after the
    # "agent -> supervisor" edge) ends the turn instead of reclassifying.
    _agent_responded: bool


def new_state() -> AgentState:
    return {
        "messages": [],
        "intent": None,
        "selected_category": None,
        "selected_product": None,
        "filters": {},
        "retrieved_products": [],
        "session_history": [],
        "booking_state": None,
        "_agent_responded": False,
    }
