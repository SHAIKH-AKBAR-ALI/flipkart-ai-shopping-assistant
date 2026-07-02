"""Web price lookup for live (web_source) products that carry no Indian price.

The MobileAPI/TechSpecs fallbacks return spec-only records with price 0.0 —
they can be shown/compared but not booked, because an order needs a real
price. This module fetches an *estimated* INR price off the open web via
Tavily, then has the LLM extract a single numeric rupee figure from the
snippets with a confidence rating.

This is deliberately an ESTIMATE, never a verified catalog price. Callers
must surface it as such to the user and require explicit confirmation before
booking at it. Low-confidence / non-INR / not-found all return None so the
caller can fall back to refusing the booking.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_MIN_PRICE = 1000.0        # below this for a phone/laptop/TV = almost certainly a parse error
_MAX_PRICE = 5_000_000.0   # above this = parse error (grabbed a phone number, model no., etc.)


def _make_client():
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.error("price_lookup: TAVILY_API_KEY not set, skipping web price lookup.")
        return None
    try:
        from tavily import TavilyClient
    except ImportError:
        logger.error("price_lookup: tavily-python not installed, skipping web price lookup.")
        return None
    try:
        return TavilyClient(api_key=api_key)
    except Exception:
        logger.exception("price_lookup: failed to construct TavilyClient.")
        return None


def _search_snippets(client, query: str) -> str:
    """Run a Tavily search and concatenate the result snippets into one blob."""
    try:
        resp = client.search(
            query=query,
            search_depth="basic",
            max_results=6,
            include_answer=True,
        )
    except Exception:
        logger.exception("price_lookup: Tavily search failed for query=%r", query)
        return ""

    parts = []
    answer = resp.get("answer")
    if answer:
        parts.append(f"SUMMARY: {answer}")
    for r in resp.get("results", []):
        title = r.get("title", "")
        content = r.get("content", "")
        if content:
            parts.append(f"[{title}] {content}")
    return "\n".join(parts)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_price(llm, product_name: str, snippets: str) -> Optional[Dict[str, Any]]:
    """Ask the LLM for a single INR price + confidence from the web snippets.

    Returns {"price": float, "confidence": "high|medium|low"} or None."""
    if llm is None or not snippets.strip():
        return None

    from langchain_core.messages import HumanMessage, SystemMessage

    system = (
        "You extract the current retail price in Indian Rupees (INR) for a "
        "specific product from web search snippets. Rules:\n"
        "- Return ONLY the price in INR as a plain number (no currency symbol, "
        "no commas).\n"
        "- If prices are given in another currency (USD, etc.), do NOT convert "
        "and treat as not found.\n"
        "- If snippets show a range or several variants, pick the lowest clearly "
        "stated INR price for the base variant.\n"
        "- If no clear INR price for THIS product is present, report not found.\n"
        'Respond as strict JSON: {"price": <number or null>, "confidence": '
        '"high"|"medium"|"low", "currency": "INR"|"other"|"none"}.'
    )
    user = f"Product: {product_name}\n\nWeb snippets:\n{snippets}"

    try:
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception:
        logger.exception("price_lookup: LLM price extraction failed.")
        return None

    m = _JSON_RE.search(text or "")
    if not m:
        logger.warning("price_lookup: no JSON in LLM output: %r", text)
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        logger.warning("price_lookup: bad JSON in LLM output: %r", text)
        return None

    if data.get("currency") != "INR":
        return None
    price = data.get("price")
    confidence = data.get("confidence", "low")
    if price is None:
        return None
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None

    if not (_MIN_PRICE <= price <= _MAX_PRICE):
        logger.warning("price_lookup: price %s out of sane range, rejecting.", price)
        return None
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    return {"price": round(price, 2), "confidence": confidence}


def lookup_inr_price(
    product_name: str, brand: str = "", llm=None
) -> Optional[Dict[str, Any]]:
    """Best-effort estimated INR price for a live/web product.

    Returns {"price": float, "confidence": "high|medium|low"} on success,
    or None if the price can't be established (no key, no results, non-INR,
    low signal, out of range). Callers must treat the price as an estimate
    and confirm with the user before booking. Low confidence is returned to
    the caller (not silently accepted) so it can decide the policy."""
    client = _make_client()
    if client is None:
        return None

    query = f"{brand} {product_name} price in India INR".strip()
    snippets = _search_snippets(client, query)
    if not snippets:
        return None

    result = _extract_price(llm, product_name, snippets)
    if result is None:
        return None

    logger.info(
        "price_lookup: %r -> Rs.%s (confidence=%s)",
        product_name, result["price"], result["confidence"],
    )
    return result
