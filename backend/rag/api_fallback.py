"""Live-API fallback for Sales/Technical agents when the local catalog comes up
short (<2 results). Two upstream sources:

- MobileAPI (mobileapi.dev)      — mobiles only
- TechSpecs (api.techspecs.io)   — laptops, TVs, smartwatches

Standalone by design: no imports from rag/retriever.py at module scope (that
would risk a circular import since retriever.py doesn't import this module,
but api_fallback needs one *symbol* from it — the cross-encoder reranker
factory — so that import is done lazily inside the rerank function instead).
Every public entry point swallows all exceptions and returns [] rather than
letting a flaky upstream API crash the agent turn.
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5
_TOP_N = 4

_MOBILE_API_URL = "https://api.mobileapi.dev/devices/search"
_TECHSPECS_API_URL = "https://api.techspecs.io/v5/products/search"

# TechSpecs categories are: Smartphones, Tablets, Smartwatches, Laptops,
# Desktops — there is NO TV category. Only map what actually exists; a TV
# query is sent with no category filter (search across everything and let
# the reranker surface the closest matches) rather than being forced into
# "Smartphones", which returned phones for a TV query.
_TECHSPECS_CATEGORY_MAP = {
    "Laptop": "Laptops",
    "Smartwatch": "Smartwatches",
    "Smart Watch": "Smartwatches",
}


def _rerank_documents(
    query: str, results: List[Dict[str, Any]], reranker: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """Rerank web_source results with the cross-encoder.

    Prefers a `reranker` instance passed in by the caller (the one already
    loaded by HybridRetriever) — that avoids re-downloading and re-loading
    the model from the HF hub on every fallback call. Falls back to lazily
    constructing its own only when called standalone with no instance. The
    CrossEncoder import stays function-scoped so this module keeps no
    import-time dependency on the heavier rag/retriever.py.
    """
    if not results:
        return []
    try:
        if reranker is None:
            from sentence_transformers import CrossEncoder

            from rag.config import RERANKER_MODEL

            reranker = CrossEncoder(RERANKER_MODEL)
        pairs = [(query, item.get("content", "")) for item in results]
        scores = reranker.predict(pairs)
        for item, score in zip(results, scores):
            item["rerank_score"] = float(score)
        results.sort(key=lambda item: item["rerank_score"], reverse=True)
    except Exception:
        logger.exception("api_fallback: reranking failed, returning unranked results.")
    return results[:_TOP_N]


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _join_specs(parts: List[str]) -> str:
    return " | ".join(p for p in parts if p)


def _make_product_id(category: str, brand: str, name: str) -> str:
    # Same deterministic scheme as rag/ingestion.py's catalog product_id —
    # required for the frontend compare-checkbox flow, which keys selection
    # state and its productIndex map by product_id. Without one, every
    # fallback card rendered with the same empty id and "Compare" silently
    # no-op'd (productIndex.get("") -> undefined, filtered out below 2).
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{category}:{brand}:{name}"))


class MobileAPIFallback:
    """Wraps mobileapi.dev — mobiles only."""

    @staticmethod
    def search(query: str, reranker: Optional[Any] = None) -> List[Dict[str, Any]]:
        api_key = os.getenv("MOBILE_API_KEY")
        if not api_key:
            logger.error("api_fallback: MOBILE_API_KEY not set, skipping MobileAPI fallback.")
            return []

        try:
            response = requests.get(
                _MOBILE_API_URL,
                params={"name": query, "key": api_key},
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception("api_fallback: MobileAPI request failed for query=%r", query)
            return []

        try:
            raw_items = MobileAPIFallback._extract_items(payload)
            parsed = [MobileAPIFallback._parse_item(item) for item in raw_items]
            parsed = [p for p in parsed if p is not None]
            return _rerank_documents(query, parsed, reranker)
        except Exception:
            logger.exception("api_fallback: MobileAPI response parsing failed for query=%r", query)
            return []

    @staticmethod
    def _extract_items(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("devices", "results", "data", "products", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _parse_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Real api.mobileapi.dev/devices/search response fields (confirmed
        # live): id, name, manufacturer_name, device_type, model_numbers,
        # colors, storage, screen_resolution, weight, thickness,
        # release_date, camera, battery_capacity, hardware, image_b64.
        # No price/rating field exists at all — always 0.0 for this source.
        if not isinstance(item, dict):
            return None

        name = item.get("name") or item.get("product_name") or item.get("title")
        if not name:
            return None

        brand = item.get("manufacturer_name") or item.get("brand") or "Unknown"
        price = _to_float(item.get("price"))
        rating = _to_float(item.get("rating"))

        content = _join_specs(
            [
                f"Display: {item.get('screen_resolution', '')}",
                f"Camera: {item.get('camera', '')}",
                f"Hardware: {item.get('hardware', '')}",
                f"Battery: {item.get('battery_capacity', '')}",
                f"Storage: {item.get('storage', '')}",
                f"Weight: {item.get('weight', '')}",
            ]
        )

        image_b64 = item.get("image_b64")
        image_url = f"data:image/jpeg;base64,{image_b64}" if image_b64 else ""

        return {
            "product_id": _make_product_id("Mobile", str(brand), str(name)),
            "product_name": str(name),
            "brand": str(brand),
            "category": "Mobile",
            "price": price,
            "rating": rating,
            "content": content or str(name),
            "image_url": image_url,
            "web_source": True,
        }


class TechSpecsFallback:
    """Wraps api.techspecs.io — laptops, TVs, smartwatches.

    Auth per techspecs.readme.io/reference/search-products: headers
    `x-api-id` and `x-api-key`, GET https://api.techspecs.io/v5/products/search
    with query params `query` (product name) and `page` (required, 0-indexed).
    TechSpecs has no Indian pricing/rating data, so those are always 0.0.
    """

    @staticmethod
    def search(query: str, category: str, reranker: Optional[Any] = None) -> List[Dict[str, Any]]:
        api_id = os.getenv("TECHSPECS_API_ID")
        api_key = os.getenv("TECHSPECS_API_KEY")
        if not api_id or not api_key:
            logger.error(
                "api_fallback: TECHSPECS_API_ID/TECHSPECS_API_KEY not set, "
                "skipping TechSpecs fallback."
            )
            return []

        # TechSpecs rejects size < 10 ("Number must be greater than or equal
        # to 10" — confirmed live); over-fetch and truncate to _TOP_N after rerank.
        params: Dict[str, Any] = {"query": query, "page": 0, "size": 10}
        techspecs_category = _TECHSPECS_CATEGORY_MAP.get(category)
        if techspecs_category:
            params["category"] = techspecs_category

        try:
            response = requests.get(
                _TECHSPECS_API_URL,
                headers={"x-api-id": api_id, "x-api-key": api_key},
                params=params,
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception(
                "api_fallback: TechSpecs request failed for query=%r category=%r",
                query,
                category,
            )
            return []

        try:
            raw_items = TechSpecsFallback._extract_items(payload)
            parsed = [
                TechSpecsFallback._parse_item(item, category) for item in raw_items
            ]
            parsed = [p for p in parsed if p is not None]
            return _rerank_documents(query, parsed, reranker)
        except Exception:
            logger.exception(
                "api_fallback: TechSpecs response parsing failed for query=%r", query
            )
            return []

    @staticmethod
    def _extract_items(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("results", "data", "products", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _parse_item(item: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
        # Real /v5/products/search response (confirmed live): each item is
        # {"Product": {"id","Brand","Category","Model","Version","Thumbnail"},
        # "Release Date": ..., "Image": <usually a placeholder string, not a
        # real URL — the "Product Detail" endpoint's Image API is a separate,
        # unrequested call>}. This search endpoint does NOT return rich specs
        # (display/camera/etc.) — those live behind /reference/product-detail
        # keyed by id, which is out of scope here (spec asked for name search
        # only). So content is built from whatever identity fields exist.
        if not isinstance(item, dict):
            return None

        product = item.get("Product") if isinstance(item.get("Product"), dict) else item
        name = product.get("Model") or product.get("name") or product.get("product_name")
        if not name:
            return None

        brand = product.get("Brand") or product.get("brand") or "Unknown"

        parts = [
            f"Model: {product.get('Model', '')}",
            f"Version: {product.get('Version', '')}",
            f"Release Date: {item.get('Release Date', '')}",
        ]
        content = _join_specs(parts)

        image_raw = item.get("Image") or product.get("Thumbnail") or ""
        image_url = image_raw if isinstance(image_raw, str) and image_raw.startswith("http") else ""

        return {
            "product_id": _make_product_id(category, str(brand), str(name)),
            "product_name": str(name),
            "brand": str(brand),
            "category": category,
            "price": 0.0,
            "rating": 0.0,
            "content": content or str(name),
            "image_url": image_url,
            "web_source": True,
        }
