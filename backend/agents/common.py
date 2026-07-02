from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.state import AgentState
from rag.api_fallback import MobileAPIFallback, TechSpecsFallback


def build_retrieval_filters(state: AgentState) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if state.get("selected_category"):
        filters["category"] = state["selected_category"]
    filters.update(state.get("filters") or {})
    return filters


def format_products_for_prompt(products: List[Dict[str, Any]]) -> str:
    if not products:
        return "No matching products found in the catalog."
    lines = [f"Found {len(products)} product(s):"]
    for p in products:
        lines.append(
            f"- {p.get('product_name')} | Brand: {p.get('brand')} | "
            f"Category: {p.get('category')} | Price: Rs.{p.get('price')} | "
            f"Rating: {p.get('rating')}"
        )
    return "\n".join(lines)


def run_retrieval_agent(
    state: AgentState,
    retriever,
    llm,
    system_prompt: str,
    reuse_existing_products: bool = False,
) -> AgentState:
    messages = state.get("messages", [])
    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )

    existing_products = state.get("retrieved_products") or []
    if reuse_existing_products and existing_products:
        products = existing_products
    else:
        filters = build_retrieval_filters(state)
        products = retriever.retrieve(last_human, filters=filters)
        if len(products) < 2:
            category = state.get("selected_category")
            if category == "Mobile":
                products = MobileAPIFallback.search(last_human)
            elif category in ("Laptop", "TV", "Smartwatch", "Smart Watch"):
                products = TechSpecsFallback.search(last_human, category)
            # Refrigerator/Washing Machine: no fallback source, keep catalog
            # results as-is (possibly empty or a single item).
    context = format_products_for_prompt(products)

    llm_response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Product catalog context:\n{context}\n\nUser question: {last_human}"),
        ]
    )
    reply_text = llm_response.content

    new_state = dict(state)
    new_state["retrieved_products"] = products
    # Auto-select only when there's a single result — no ambiguity. When
    # multiple products come back, leave selected_product unset so a later
    # booking request triggers disambiguation instead of silently picking
    # the top-ranked one.
    if not new_state.get("selected_product") and len(products) == 1:
        new_state["selected_product"] = products[0]
    new_state["messages"] = messages + [AIMessage(content=reply_text)]
    new_state["_agent_responded"] = True
    new_state["_last_response"] = {"message": reply_text, "retrieved_products": products}
    return new_state
