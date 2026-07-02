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
# Product-line words users type instead of the canonical brand — "iphone"
# means Apple, "galaxy" means Samsung, etc. Needed so a brand-only query
# ("iphone above 50k") can be matched against a stale result set's brands
# even though the word "iphone" is never itself in PREDEFINED_BRANDS.
_BRAND_ALIASES = {
    "iphone": "apple", "macbook": "apple", "ipad": "apple",
    "galaxy": "samsung",
    "redmi": "xiaomi", "poco": "xiaomi",
    "pixel": "google",
    "thinkpad": "lenovo", "ideapad": "lenovo",
    "nothing": "nothing",
}
# Category words ("mobiles", "laptop"...) are already enforced by the
# retrieval filter — like brand words, they're never a distinguishing
# signal in a top-hit's product name, so they'd otherwise cause a false
# "not a miss" or false "miss" depending on phrasing without adding anything.
_CATEGORY_WORDS = {kw for kws in _CATEGORY_KEYWORDS.values() for kw in kws}


def _normalize_letter_digit_spacing(query: str) -> str:
    # Typed-without-spaces model numbers ("17pro", "iphone17") tokenize as one
    # non-digit blob and don't match either external API's fuzzy search, or
    # a catalog product name's separately-spaced tokens. Split letter/digit
    # runs apart before tokenizing anywhere query text needs to be compared.
    normalized = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", query)
    normalized = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", normalized)
    return normalized


def _query_keywords(query: str) -> List[str]:
    # Brand and category tokens are excluded — "iPhone 17" vs a catalog
    # top-hit of "iPhone 13" would otherwise "overlap" on the shared brand
    # alone and never register as a miss, even though the model is wrong.
    tokens = re.findall(r"[a-z0-9]+", _normalize_letter_digit_spacing(query).lower())
    return [
        t for t in tokens
        if len(t) > 1 and t not in _STOPWORDS and t not in _BRAND_WORDS and t not in _CATEGORY_WORDS
    ]


# Words that qualify a model within a product line ("iPhone 17 PRO MAX",
# "Galaxy S23 ULTRA", "ThinkPad X1 CARBON"). Kept in the fallback query.
_MODEL_QUALIFIERS = {
    "pro", "max", "plus", "ultra", "mini", "air", "se", "lite", "note",
    "edge", "fold", "flip", "neo", "ace", "prime", "series", "gt", "turbo",
    "active", "fe", "carbon", "gen",
}


def _clean_product_query(query: str) -> str:
    """MobileAPI/TechSpecs are keyword/fuzzy search, not semantic — a raw
    chat sentence ("tell me about the iPhone camera") drowns the one word
    that matters ("iphone") in filler and scores 0 matches.

    When the query names a brand/product-line, build the search string from
    only the product-signal tokens: the brand/alias, model qualifiers, and
    small digits (model generation / storage — not budget amounts). This
    turns "tell me about iphone camera" into "iphone" and "iphone 17 pro max"
    into itself. When no brand is named, fall back to a filler-word strip so
    generic queries still send something."""
    tokens = re.findall(r"[A-Za-z0-9]+", _normalize_letter_digit_spacing(query))

    signal: List[str] = []
    has_brand = False
    for tok in tokens:
        lo = tok.lower()
        if lo in _BRAND_WORDS or lo in _BRAND_ALIASES:
            signal.append(tok)
            has_brand = True
        elif lo in _MODEL_QUALIFIERS:
            signal.append(tok)
        elif lo.isdigit() and int(lo) < 2000:
            # Small numbers are model gen / storage (17, 256). Larger ones
            # are budget amounts (20000, 50000) — noise for a name search.
            signal.append(tok)

    if has_brand and signal:
        return " ".join(signal)

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


def _reuse_miss(query: str, existing_products: List[Dict[str, Any]]) -> bool:
    """Technical Agent normally reuses retrieved_products from state instead
    of re-retrieving (so "compare these"/"which has a better camera" reasons
    over the same set). But if the query names a specific product/model that
    isn't anywhere in that stale set, reusing it silently answers about the
    wrong product.

    Two "specific product" signals count as a miss when absent from the
    stale set: (a) a model number ("iphone 17" but state has only 13/15),
    same digit-priority reasoning as _is_catalog_miss; (b) a brand/product-
    line the state doesn't contain ("iphone above 50k" but state has only
    Samsung/Nothing). Generic follow-ups ("compare these", "which has a
    better camera") have neither and must keep reusing state, or the
    compare/follow-up flow Technical Agent is built around breaks."""
    names_blob = " ".join((p.get("product_name") or "").lower() for p in existing_products)

    digit_keywords = [kw for kw in _query_keywords(query) if kw.isdigit()]
    if digit_keywords and not any(kw in names_blob for kw in digit_keywords):
        return True

    query_brands = _query_brands(query)
    if query_brands:
        existing_brands = {(p.get("brand") or "").lower() for p in existing_products}
        brand_blob = names_blob + " " + " ".join(existing_brands)
        if not any(b in brand_blob for b in query_brands):
            return True

    return False


def _query_brands(query: str) -> set:
    """Brands/product-lines named in the query, resolved to canonical brand
    (lowercase). "iphone" -> apple, "samsung" -> samsung."""
    tokens = set(re.findall(r"[a-z0-9]+", _normalize_letter_digit_spacing(query).lower()))
    found = set()
    for b in _BRAND_WORDS:
        if b in tokens:
            found.add(b)
    for alias, canon in _BRAND_ALIASES.items():
        if alias in tokens:
            found.add(canon)
    return found


def _has_product_signal(query: str, filters: Dict[str, Any]) -> bool:
    """Does the query actually name a product to look up? A brand/product-line,
    a model qualifier (pro/ultra/...), or a model-number digit that isn't a
    budget/rating value. A bare budget query ("mobiles above 50k") has none —
    there's nothing to search a name-based API for, so firing the fallback
    just returns unrelated junk. Gate the external lookup on this."""
    if _query_brands(query):
        return True
    filter_digits = _filter_digit_tokens(filters)
    tokens = re.findall(r"[a-z0-9]+", _normalize_letter_digit_spacing(query).lower())
    for t in tokens:
        if t in _MODEL_QUALIFIERS:
            return True
        if t.isdigit() and t not in filter_digits and int(t) < 2000:
            return True
    return False


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
    if reuse_existing_products and existing_products and not _reuse_miss(last_human, existing_products):
        products = existing_products
    else:
        filters = build_retrieval_filters(state)
        products = retriever.retrieve(last_human, filters=filters)
        # Only reach for the external name-search API when the catalog fell
        # short AND the query actually names a product. A bare budget query
        # ("mobiles above 50k") that misses the catalog has nothing to search
        # for — firing the fallback there just returns unrelated phones.
        if _is_catalog_miss(last_human, products, filters) and _has_product_signal(last_human, filters):
            category = state.get("selected_category")
            fallback_query = _clean_product_query(last_human)
            # Reuse the retriever's already-loaded cross-encoder for reranking
            # web results — avoids re-loading the model from HF on every call.
            reranker = retriever.get_reranker() if hasattr(retriever, "get_reranker") else None
            if category == "Mobile":
                products = MobileAPIFallback.search(fallback_query, reranker=reranker)
            elif category in ("Laptop", "TV", "Smartwatch", "Smart Watch"):
                products = TechSpecsFallback.search(fallback_query, category, reranker=reranker)
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
