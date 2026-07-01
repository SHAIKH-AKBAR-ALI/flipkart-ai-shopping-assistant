# Version 2 RAG Module

This package implements the LlamaIndex-based retrieval system for the Flipkart AI Shopping Assistant.

## Sub-module Responsibilities
- `config.py`: Local parameters (top-K, reranker model).
- `models.py`: Shared data model schemas.
- `embeddings.py`: Configures local HuggingFace embedding models.
- `ingestion.py`: Cleans raw CSV datasets and populates the AstraDB collection.
- `retriever.py`: Hybrid search (dense AstraDB + sparse BM25), Rank Fusion, and Reranking.
- `query_engine.py`: Wrap and run queries through the LlamaIndex query context.

## Development Guidelines
*   **Imports**: Since `requirements.txt` installs `llama-index-core` (v0.10+ standalone layout) instead of the legacy monolithic package, **all LlamaIndex imports must target the `.core` namespace** (e.g., `from llama_index.core import Document`). Do not import from the top-level `llama_index` wrapper package.

## Implementation Order
1. **Phase 3.1**: Scaffolding & LlamaIndex Foundation (Current)
2. **Phase 3.2**: Vector Store Configuration & Database Connection Testing
3. **Phase 3.3**: Data Cleaning & Ingestion Pipeline Setup
4. **Phase 3.4**: Local Embedding Setup & Document Vector Indexing
5. **Phase 3.5**: Pre-Filtered Hybrid Retriever Implementation
6. **Phase 3.6**: Reciprocal Rank Fusion & CPU Cross-Encoder Reranking
