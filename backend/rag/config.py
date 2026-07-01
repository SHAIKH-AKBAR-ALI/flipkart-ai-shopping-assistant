# RAG Configuration constants
from typing import Optional

EMBEDDING_MODEL: Optional[str] = "sentence-transformers/all-MiniLM-L6-v2"
RERANKER_MODEL: Optional[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DENSE_SEARCH_K: Optional[int] = 20
BM25_SEARCH_K: Optional[int] = 20
RRF_MERGE_SIZE: Optional[int] = 30
RERANKER_INPUT_SIZE: Optional[int] = 15
FINAL_TOP_N: Optional[int] = 4
CACHE_SIZE: Optional[int] = 100
