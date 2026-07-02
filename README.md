# Flipkart AI Shopping Assistant

A RAG-powered, multi-agent shopping assistant for Flipkart product catalogs — a LangGraph Supervisor routes every message to a Sales, Technical, or Booking agent, backed by a hybrid dense + BM25 retrieval pipeline over AstraDB.

**Live demo:** [Frontend URL] | [Backend URL] <!-- fill in after deploy -->

![Screenshot](docs/screenshot.png) <!-- add screenshot after deploy -->

---

## What it does

- **6 product categories** — Laptops, Mobiles, TVs, Refrigerators, Smart Watches, Washing Machines — each with its own chat context (sessions never leak across categories).
- **3 specialized agents**, routed per turn by a Supervisor:
  - **Sales Agent** — pricing, EMI, offers, budget-driven recommendations
  - **Technical Agent** — specs, comparisons ("compare these", "which has a better camera") over the products already retrieved, without re-querying
  - **Booking Agent** — a deterministic state machine that disambiguates the product, collects name/address/phone/payment, and hands off to a mock payment page before confirming the order
- **Hybrid RAG pipeline** — metadata filters (category / budget / rating) applied *before* retrieval, dense vector search (AstraDB) fused with BM25 via Reciprocal Rank Fusion, then reranked with a cross-encoder to a final top 4.
- **Live-data fallback** — when the catalog can't answer, external product APIs (MobileAPI, TechSpecs) fill in, with a web price lookup via Tavily.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | [Astro](https://astro.build) (static output, vanilla JS islands), Tailwind CSS v4 |
| Backend | [FastAPI](https://fastapi.tiangolo.com) |
| Orchestration | [LangGraph](https://langchain-ai.github.io/langgraph/) (Supervisor + 3 agent nodes) |
| LLM | [Groq](https://groq.com) — `llama-3.3-70b-versatile` via `langchain-groq` |
| Ingestion | [LlamaIndex](https://www.llamaindex.ai) document pipeline |
| Vector DB | [DataStax AstraDB](https://www.datastax.com/products/datastax-astra) (queried directly via `astrapy`) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local CPU) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local CPU) |
| Keyword search | `rank-bm25` |
| Live product data | MobileAPI, TechSpecs (catalog fallback) |
| Sessions | SQLite via SQLAlchemy |
| Observability | LangSmith tracing (optional) |

## Architecture

### Multi-agent graph

```
START → Supervisor → (sales | technical | booking | clarify)
             ↑              │
             └── sub-agent ─┘   (Supervisor's second visit ends the turn)
```

The Supervisor classifies intent with the LLM (keyword-match fallback if the call fails), extracts category/budget/rating filters from the message, and carries them forward in session state. A booking flow already in progress owns the next turn outright — replies like "the third one" can't be re-classified out of context.

### Retrieval pipeline

```
query
  ↓  metadata filter (category / budget / rating) — applied BEFORE retrieval
  ├─ Dense search (AstraDB, K=20)
  └─ BM25 (pre-filtered in-memory corpus, K=20)
  ↓  Reciprocal Rank Fusion (k=60)
  ↓  Cross-encoder rerank → top 4
```

Filters are pushed down into both search paths — never applied post-hoc over an unfiltered result set — so a "laptops under ₹50,000" query is scored only against laptops under ₹50,000.

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [DataStax AstraDB](https://astra.datastax.com) database and a [Groq](https://console.groq.com) API key

### 1. Clone

```bash
git clone <repo-url>
cd flipkart-rag-v2
```

### 2. Backend

Create `backend/.env`:

```env
GROQ_API_KEY=
ASTRA_DB_API_ENDPOINT=
ASTRA_DB_APPLICATION_TOKEN=
ASTRA_DB_KEYSPACE=
ASTRA_DB_COLLECTION=

# External catalog-fallback APIs
MOBILE_API_KEY=
TECHSPECS_API_ID=
TECHSPECS_API_KEY=

# LangSmith tracing (optional)
LANGCHAIN_TRACING_V2=
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=

# CORS (comma-separated; defaults to http://localhost:4321 if unset)
ALLOWED_ORIGINS=
```

Install and run:

```bash
cd backend
pip install -r requirements.txt
uvicorn app_v2:app --reload
```

The API starts on `http://localhost:8000`; heavy initialization (embeddings, BM25 corpus, graph compilation) happens in the background — poll `/ready` until it returns `{"ready": true}`.

### 3. Frontend

```bash
cd frontend-astro
npm install
npm run dev
```

Opens on `http://localhost:4321`, pointed at `http://localhost:8000` by default (override with `PUBLIC_API_BASE_URL`).

## Known limitations

- **TV category fallback is weak** — the external catalog APIs cover mobiles well but TV lookups often return thin or no data, so TV answers lean almost entirely on the ingested CSV catalog.
- **Budget filters reset on product switch** — a budget range that contradicts the previous one is treated as a fresh filter context (by design, to avoid impossible min > max ranges), so earlier constraints don't carry over.
- **MobileAPI occasionally returns 0 results on noisy queries** — long or heavily qualified product names can miss; the assistant falls back to catalog data when that happens.

## License

MIT
