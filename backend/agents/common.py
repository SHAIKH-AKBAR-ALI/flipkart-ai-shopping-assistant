import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.state import AgentState
from agents.supervisor import _CATEGORY_KEYWORDS
from rag.api_fallback import MobileAPIFallback, TechSpecsFallback
from rag.ingestion import PREDEFINED_BRANDS

_STOPWORDS = {
    "i", "want", "to", "buy", "the", "a", "an", "is", "of", "for", "in", "on",
    "with", "please", "show", "me", "find", "looking", "need", "get", "book",
    "order", "purchase", "about", "and", "or", "from",
}
_BRAND_WORDS = {b.lower() for b in PREDEFINED_BRANDS}
# Category words ("mobiles", "laptop"...) are already enforced by the
# retrieval filter — like brand words, they're never a distinguishing
# signal in a top-hit's product name, so they'd otherwise cause a false
# "not a miss" or false "miss" depending on phrasing without adding anything.
_CATEGORY_WORDS = {kw for kws in _CATEGORY_KEYWORDS.values() for kw in kws}


def _query_keywords(query: str) -> List[str]:
    # Brand and category tokens are excluded — "iPhone 17" vs a catalog
    # top-hit of "iPhone 13" would otherwise "overlap" on the shared brand
    # alone and never register as a miss, even though the model is wrong.
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    return [
        t for t in tokens
        if len(t) > 1 and t not in _STOPWORDS and t not in _BRAND_WORDS and t not in _CATEGORY_WORDS
    ]


def _clean_product_query(query: str) -> str:
    """MobileAPI/TechSpecs are keyword/fuzzy search, not semantic — a raw
    chat sentence ("I want to buy iPhone 17 Pro Max") scores 0 matches on
    both even though "iPhone 17 Pro Max" alone finds it. Strip filler words,
    keep original casing/order for the rest."""
    tokens = re.findall(r"[A-Za-z0-9]+", query)
    filtered = [t for t in tokens if t.lower() not in _STOPWORDS]
    return " ".join(filtered) if filtered else query


def _filter_digit_tokens(filters: Dict[str, Any]) -> set:
    # Budget/rating values already extracted into filters (e.g. "20000" from
    # "from 20000 to 35000") aren't model numbers — they're already applied
    # as a metadata filter on the retrieve() call. Exclude them so the
    # digit-priority check below only reacts to real model-number tokens.
    tokens = set()
    for key in ("budget_min", "budget_max", "min_rating"):
        value = filters.get(key)
        if value is None:
            continue
        tokens.add(str(int(value)) if value == int(value) else str(value))
    return tokens


def _is_catalog_miss(query: str, products: List[Dict[str, Any]], filters: Dict[str, Any]) -> bool:
    if len(products) < 2:
        return True
    keywords = _query_keywords(query)
    if not keywords:
        return False
    top_name = (products[0].get("product_name") or "").lower()

    # Numbers already consumed as a budget/rating filter value aren't model
    # numbers — "20000"/"35000" from "from 20000 to 35000" are a price range,
    # already applied on the retrieve() call, not something the product NAME
    # is expected to contain. Drop them before either check below runs.
    filter_digits = _filter_digit_tokens(filters)
    remaining_keywords = [kw for kw in keywords if not (kw.isdigit() and kw in filter_digits)]
    if not remaining_keywords:
        return False

    # Numbers carry the real distinguishing signal for tech products (model
    # generation, storage size...) — "iPhone 17" vs a top-hit of "iPhone 13"
    # would otherwise still register as a keyword match on "iphone" alone
    # (it isn't in PREDEFINED_BRANDS; "Apple" is), missing exactly the case
    # this check exists for. When the query has a (non-filter) number,
    # require it — not just any keyword — to appear in the top hit.
    digit_keywords = [kw for kw in remaining_keywords if kw.isdigit()]
    if digit_keywords:
        return not any(kw in top_name for kw in digit_keywords)
    return not any(kw in top_name for kw in remaining_keywords)


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
        if _is_catalog_miss(last_human, products, filters):
            category = state.get("selected_category")
            fallback_query = _clean_product_query(last_human)
            if category == "Mobile":
                products = MobileAPIFallback.search(fallback_query)
            elif category in ("Laptop", "TV", "Smartwatch", "Smart Watch"):
                products = TechSpecsFallback.search(fallback_query, category)
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
