from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.state import AgentState


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
) -> AgentState:
    messages = state.get("messages", [])
    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )

    filters = build_retrieval_filters(state)
    products = retriever.retrieve(last_human, filters=filters)
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
    # Auto-select the top-ranked result as "the product being discussed" if the
    # user hasn't explicitly picked one yet — needed so a follow-up like "how's
    # the camera on this one?" has something for selected_product to refer to.
    if not new_state.get("selected_product") and products:
        new_state["selected_product"] = products[0]
    new_state["messages"] = messages + [AIMessage(content=reply_text)]
    new_state["_agent_responded"] = True
    new_state["_last_response"] = {"message": reply_text, "retrieved_products": products}
    return new_state
