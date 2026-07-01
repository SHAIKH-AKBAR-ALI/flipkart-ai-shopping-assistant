import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from rag.config import (
    BM25_SEARCH_K,
    CACHE_SIZE,
    DENSE_SEARCH_K,
    FINAL_TOP_N,
    RERANKER_INPUT_SIZE,
    RERANKER_MODEL,
    RRF_MERGE_SIZE,
)
from rag.embeddings import EmbeddingManager
from rag.ingestion import ProductDataPipeline

# Standard damping constant for Reciprocal Rank Fusion (Cormack et al. 2009).
# Not a search-size parameter, so it isn't in config.py; it's inherent to the RRF formula.
RRF_K = 60

# Category names in CLAUDE.md/product briefs are plural ("Laptops", "Mobiles"...),
# but rag/ingestion.py's _detect_category_from_filename stores singular values
# ("Laptop", "Mobile", "TV", "Refrigerator", "Smart Watch", "Washing Machine").
# Normalizing user-facing filter input to what's actually stored.
_CATEGORY_ALIASES = {
    "laptops": "Laptop",
    "laptop": "Laptop",
    "mobiles": "Mobile",
    "mobile": "Mobile",
    "tvs": "TV",
    "tv": "TV",
    "refrigerators": "Refrigerator",
    "refrigerator": "Refrigerator",
    "smart watches": "Smart Watch",
    "smart watch": "Smart Watch",
    "washing machines": "Washing Machine",
    "washing machine": "Washing Machine",
}


def _normalize_category(value: str) -> str:
    return _CATEGORY_ALIASES.get(value.strip().lower(), value.strip())


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class HybridRetriever:
    def __init__(self):
        endpoint = os.getenv("ASTRA_DB_API_ENDPOINT")
        token = os.getenv("ASTRA_DB_APPLICATION_TOKEN")
        keyspace = os.getenv("ASTRA_DB_KEYSPACE", "default_keyspace")
        collection_name = os.getenv("ASTRA_DB_COLLECTION", "flipkart_reviews")
        if not endpoint or not token:
            raise ValueError(
                "Missing AstraDB connection variables "
                "(ASTRA_DB_API_ENDPOINT or ASTRA_DB_APPLICATION_TOKEN)"
            )

        # Talk to astrapy directly (not llama_index's AstraDBVectorStore wrapper):
        # that wrapper's _query_filters_to_dict only supports FilterOperator.EQ,
        # which can't express budget/rating range filters natively.
        from astrapy import DataAPIClient

        self._collection = DataAPIClient(token).get_database(
            endpoint, keyspace=keyspace
        ).get_collection(collection_name)

        self._embedder = EmbeddingManager()
        self._reranker: Optional[CrossEncoder] = None

        # In-memory corpus for BM25 — same source ingestion.py uses to populate AstraDB.
        documents = ProductDataPipeline().load_and_build_documents()
        self._corpus: List[Dict[str, Any]] = []
        for doc in documents:
            meta = doc.metadata
            self._corpus.append(
                {
                    "product_id": meta["product_id"],
                    "product_name": meta["product_name"],
                    "brand": meta["brand"],
                    "category": meta["category"],
                    "price": meta["price"],
                    "rating": meta["rating"],
                    "review_count": meta["review_count"],
                    "content": doc.text,
                    "tokens": _tokenize(doc.text),
                }
            )

        self._cache: "OrderedDict[tuple, List[Dict[str, Any]]]" = OrderedDict()

    def _get_reranker(self) -> CrossEncoder:
        if self._reranker is None:
            self._reranker = CrossEncoder(RERANKER_MODEL)
        return self._reranker

    @staticmethod
    def _matches_filters(
        item: Dict[str, Any],
        category: Optional[str],
        min_rating: Optional[float],
        budget_min: Optional[float],
        budget_max: Optional[float],
    ) -> bool:
        if category is not None and item["category"] != category:
            return False
        if min_rating is not None and item["rating"] < min_rating:
            return False
        if budget_min is not None and item["price"] < budget_min:
            return False
        if budget_max is not None and item["price"] > budget_max:
            return False
        return True

    @staticmethod
    def _build_astra_filter(
        category: Optional[str],
        min_rating: Optional[float],
        budget_min: Optional[float],
        budget_max: Optional[float],
    ) -> Dict[str, Any]:
        astra_filter: Dict[str, Any] = {}
        if category is not None:
            astra_filter["metadata.category"] = category
        price_range: Dict[str, Any] = {}
        if budget_min is not None:
            price_range["$gte"] = budget_min
        if budget_max is not None:
            price_range["$lte"] = budget_max
        if price_range:
            astra_filter["metadata.price"] = price_range
        if min_rating is not None:
            astra_filter["metadata.rating"] = {"$gte": min_rating}
        return astra_filter

    def _dense_search(
        self,
        query: str,
        category: Optional[str],
        min_rating: Optional[float],
        budget_min: Optional[float],
        budget_max: Optional[float],
    ) -> List[Dict[str, Any]]:
        query_embedding = self._embedder.embed_query(query)
        astra_filter = self._build_astra_filter(category, min_rating, budget_min, budget_max)

        matches = list(
            self._collection.find(
                filter=astra_filter,
                sort={"$vector": query_embedding},
                limit=DENSE_SEARCH_K,
                projection={"*": True},
                include_similarity=True,
            )
        )

        results = []
        for match in matches:
            meta = match["metadata"]
            results.append(
                {
                    "product_id": meta["product_id"],
                    "product_name": meta["product_name"],
                    "brand": meta.get("brand"),
                    "category": meta["category"],
                    "price": meta["price"],
                    "rating": meta["rating"],
                    "review_count": meta.get("review_count"),
                    "content": match["content"],
                    "dense_score": match["$similarity"],
                }
            )
        return results

    def _bm25_search(
        self,
        query: str,
        category: Optional[str],
        min_rating: Optional[float],
        budget_min: Optional[float],
        budget_max: Optional[float],
    ) -> List[Dict[str, Any]]:
        subset = [
            item
            for item in self._corpus
            if self._matches_filters(item, category, min_rating, budget_min, budget_max)
        ]
        if not subset:
            return []

        bm25 = BM25Okapi([item["tokens"] for item in subset])
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(subset, scores), key=lambda pair: pair[1], reverse=True)[:BM25_SEARCH_K]

        results = []
        for item, score in ranked:
            if score <= 0:
                continue
            result = {k: v for k, v in item.items() if k != "tokens"}
            result["bm25_score"] = float(score)
            results.append(result)
        return results

    @staticmethod
    def _rrf_merge(
        dense: List[Dict[str, Any]],
        bm25: List[Dict[str, Any]],
        k: int = RRF_K,
        top_n: int = RRF_MERGE_SIZE,
    ) -> List[Dict[str, Any]]:
        rrf_scores: Dict[str, float] = {}
        docs_by_id: Dict[str, Dict[str, Any]] = {}

        for rank, item in enumerate(dense, start=1):
            pid = item["product_id"]
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + 1.0 / (k + rank)
            docs_by_id.setdefault(pid, item)

        for rank, item in enumerate(bm25, start=1):
            pid = item["product_id"]
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + 1.0 / (k + rank)
            docs_by_id.setdefault(pid, item)

        ranked_ids = sorted(rrf_scores, key=lambda pid: rrf_scores[pid], reverse=True)[:top_n]
        return [{**docs_by_id[pid], "rrf_score": rrf_scores[pid]} for pid in ranked_ids]

    def _rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        subset = candidates[:RERANKER_INPUT_SIZE]
        if not subset:
            return []

        reranker = self._get_reranker()
        pairs = [(query, item["content"]) for item in subset]
        scores = reranker.predict(pairs)

        for item, score in zip(subset, scores):
            item["rerank_score"] = float(score)

        subset.sort(key=lambda item: item["rerank_score"], reverse=True)
        return subset[:FINAL_TOP_N]

    def retrieve(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        filters = filters or {}
        category = filters.get("category")
        if category is not None:
            category = _normalize_category(category)
        min_rating = filters.get("min_rating")
        budget_min = filters.get("budget_min")
        budget_max = filters.get("budget_max")

        cache_key = (query, category, min_rating, budget_min, budget_max)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        dense_results = self._dense_search(query, category, min_rating, budget_min, budget_max)
        bm25_results = self._bm25_search(query, category, min_rating, budget_min, budget_max)

        if not dense_results and not bm25_results:
            final: List[Dict[str, Any]] = []
        else:
            merged = self._rrf_merge(dense_results, bm25_results)
            final = self._rerank(query, merged)

        self._cache[cache_key] = final
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return final
