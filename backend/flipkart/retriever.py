import time
from dataclasses import dataclass, field

from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_astradb import AstraDBVectorStore
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from flipkart import config

# Module-level BM25 cache keyed by corpus identity — survives HybridRetriever re-instantiation
_BM25_CACHE: dict[int, BM25Okapi] = {}


@dataclass
class RetrievalMetadata:
    query_variants: list[str] = field(default_factory=list)
    docs_retrieved: int = 0
    docs_after_rerank: int = 0
    retrieval_time: float = 0.0


_HYDE_PROMPT = (
    "Write a realistic 2-3 sentence product review for someone searching: '{query}'. "
    "Mention specific features, pros/cons, and a rating impression."
)

_MULTIQUERY_PROMPT = (
    "Rewrite this product search query in 1 different way to improve retrieval. "
    "Return exactly 1 line, no numbering or bullets.\n\nQuery: {query}"
)


class HybridRetriever:
    def __init__(
        self,
        vector_store: AstraDBVectorStore,
        documents: list[Document],
        use_hyde: bool = False,
    ):
        self.vector_store = vector_store
        self.documents = documents
        self.use_hyde = use_hyde

        self._embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL
        )
        self._llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
        self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

        # Query result cache: {cache_key: (docs, meta)}
        self._cache: dict[str, tuple[list[Document], RetrievalMetadata]] = {}

        corpus_id = id(documents)
        if corpus_id not in _BM25_CACHE:
            tokenized_corpus = [doc.page_content.lower().split() for doc in documents]
            _BM25_CACHE[corpus_id] = BM25Okapi(tokenized_corpus)
        self.bm25 = _BM25_CACHE[corpus_id]

    # ── Cache key ─────────────────────────────────────────────────────────────

    def _cache_key(self, query: str, filters: dict | None) -> str:
        f = f"{filters}" if filters else ""
        return f"{query.strip().lower()}|{f}"

    # ── BM25 ──────────────────────────────────────────────────────────────────

    def _bm25_search(self, query: str, k: int = config.RETRIEVER_K) -> list[Document]:
        tokens = query.lower().split()
        scores = self.bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [self.documents[i] for i in top_indices]

    # ── Dense (AstraDB) ───────────────────────────────────────────────────────

    def _dense_search(
        self,
        query: str,
        embedding_override: list[float] | None = None,
        k: int = config.RETRIEVER_K,
    ) -> list[Document]:
        if embedding_override is not None:
            return self.vector_store.similarity_search_by_vector(embedding_override, k=k)
        return self.vector_store.similarity_search(query, k=k)

    # ── HyDE ─────────────────────────────────────────────────────────────────

    def _hyde_embedding(self, query: str) -> list[float]:
        prompt = _HYDE_PROMPT.format(query=query)
        hypothetical_doc = self._llm.invoke(prompt).content
        return self._embeddings.embed_query(hypothetical_doc)

    # ── Multi-query ───────────────────────────────────────────────────────────

    def _generate_query_variants(self, query: str) -> list[str]:
        prompt = _MULTIQUERY_PROMPT.format(query=query)
        response = self._llm.invoke(prompt).content
        variants = [line.strip() for line in response.strip().splitlines() if line.strip()]
        return variants[:1]

    # ── Hybrid search for one query (sequential) ──────────────────────────────

    def _hybrid_search_one(self, query: str) -> list[Document]:
        hyde_emb = self._hyde_embedding(query) if self.use_hyde else None
        bm25_results = self._bm25_search(query)
        dense_results = self._dense_search(query, embedding_override=hyde_emb)
        return self._rrf_merge([bm25_results, dense_results])

    # ── RRF ───────────────────────────────────────────────────────────────────

    def _rrf_merge(self, result_lists: list[list[Document]], k: int = 60) -> list[Document]:
        scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for result_list in result_lists:
            for rank, doc in enumerate(result_list, start=1):
                pid = doc.metadata.get("product_id") or doc.page_content[:80]
                scores[pid] = scores.get(pid, 0.0) + 1.0 / (rank + k)
                doc_map[pid] = doc

        ranked = sorted(scores.keys(), key=lambda pid: scores[pid], reverse=True)
        return [doc_map[pid] for pid in ranked]

    # ── Filters ───────────────────────────────────────────────────────────────

    def _apply_filters(self, docs: list[Document], filters: dict | None) -> list[Document]:
        if not filters:
            return docs

        result = docs
        # Support both 'min_rating' (internal) and 'rating' (from UI)
        min_rating = filters.get("rating") or filters.get("min_rating")
        category = filters.get("category")
        budget = filters.get("budget")  # Expected: [min, max]

        if min_rating is not None:
            result = [
                d for d in result
                if d.metadata.get("rating") is not None
                and float(d.metadata["rating"]) >= float(min_rating)
            ]
        
        if budget and isinstance(budget, (list, tuple)) and len(budget) == 2:
            min_p, max_p = budget
            result = [
                d for d in result
                if d.metadata.get("price") is not None
                and float(min_p) <= float(d.metadata["price"]) <= float(max_p)
            ]

        if category:
            result = [
                d for d in result
                if d.metadata.get("category", "").lower() == category.lower()
            ]

        return result

    # ── Cross-encoder rerank ──────────────────────────────────────────────────

    def _rerank(self, query: str, docs: list[Document]) -> list[Document]:
        if not docs:
            return docs
        if len(docs) < config.RERANK_TOP_N:
            # Not enough docs to justify cross-encoder — return as-is
            return docs
        pairs = [(query, doc.page_content) for doc in docs]
        ce_scores = self._cross_encoder.predict(pairs)
        ranked = sorted(zip(ce_scores, docs), key=lambda x: x[0], reverse=True)
        return [doc for _, doc in ranked[: config.RERANK_TOP_N]]

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        filters: dict | None = None,
    ) -> tuple[list[Document], RetrievalMetadata]:
        cache_key = self._cache_key(query, filters)
        if cache_key in self._cache:
            return self._cache[cache_key]

        meta = RetrievalMetadata()
        t0 = time.perf_counter()

        variants = self._generate_query_variants(query)
        all_variants = [query] + variants
        meta.query_variants = all_variants

        # Sequential — avoids Windows thread issues
        all_results: list[list[Document]] = []
        for q in all_variants:
            all_results.append(self._hybrid_search_one(q))

        merged = self._rrf_merge(all_results)
        filtered = self._apply_filters(merged, filters)
        meta.docs_retrieved = len(filtered)

        reranked = self._rerank(query, filtered)
        meta.docs_after_rerank = len(reranked)
        meta.retrieval_time = round(time.perf_counter() - t0, 3)

        self._cache[cache_key] = (reranked, meta)
        return reranked, meta
