# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Flipkart AI Shopping Assistant V2 — a RAG-powered, multi-agent shopping
assistant covering 6 product categories (Laptops, Mobiles, TVs,
Refrigerators, Smart Watches, Washing Machines). A LangGraph Supervisor
routes each turn to a Sales, Technical, or Booking agent; retrieval is a
hybrid dense+BM25 pipeline over AstraDB reranked with a cross-encoder.
The frontend is a standalone Astro app that talks to the V2 FastAPI
backend over `/chat`. V1 (`backend/flipkart/`, `frontend/`) is a separate,
untouched prior implementation kept only for reference.

## Tech stack

- **Frontend**: Astro (static output, vanilla JS islands, no framework),
  Tailwind CSS v4 (CSS-first config via `@theme` in `global.css`, no
  `tailwind.config.js`)
- **Backend**: FastAPI (`app_v2.py`)
- **Orchestration**: LangGraph (Supervisor + 3 sub-agent nodes)
- **LLM**: Groq (`llama-3.3-70b-versatile`) via `langchain-groq`
- **Retrieval**: LlamaIndex-adjacent hybrid retriever (talks to AstraDB
  directly via `astrapy`, not LlamaIndex's vector store wrapper — see
  Decisions)
- **Vector DB**: DataStax AstraDB
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (local CPU)
- **Reranker**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (local CPU)
- **BM25**: `rank-bm25`
- **Session storage**: SQLite via SQLAlchemy (`backend/data/sessions_v2.db`)

## Backend structure

```
backend/
├── flipkart/            # V1 — DO NOT MODIFY
├── app.py                # V1 FastAPI entrypoint (imports flipkart/ only)
├── app_v2.py              # V2 FastAPI entrypoint — this is what's live
├── rag/                    # Hybrid retrieval package
│   ├── config.py            # search-size constants (K values, top-N, cache size)
│   ├── models.py             # RAGProduct pydantic schema (aspirational —
│   │                          # fields like mrp/discount/specifications aren't
│   │                          # actually populated by the retriever yet)
│   ├── embeddings.py          # EmbeddingManager (sentence-transformers wrapper)
│   ├── ingestion.py            # ProductDataPipeline — builds LlamaIndex Documents
│   │                            # from the category CSVs; also the source of the
│   │                            # in-memory BM25 corpus
│   ├── retriever.py             # HybridRetriever — dense (AstraDB) + BM25,
│   │                             # RRF merge, cross-encoder rerank
│   └── query_engine.py           # FlipkartQueryEngine (retrieval + synthesis
│                                    orchestration; not on the main /chat path)
├── agents/                 # LangGraph multi-agent package
│   ├── state.py               # AgentState TypedDict + new_state()
│   ├── supervisor.py            # intent routing (LLM + keyword fallback)
│   ├── common.py                 # run_retrieval_agent() — shared retrieval +
│   │                              # LLM-synthesis logic used by sales/technical
│   ├── sales_agent.py              # pricing/EMI/offers system prompt
│   ├── technical_agent.py           # specs/comparison system prompt, reuses
│   │                                 # retrieved_products instead of re-retrieving
│   ├── booking_agent.py              # deterministic booking state machine (no LLM
│   │                                  # except optionally phrasing the final
│   │                                  # confirmation message)
│   ├── graph.py                       # build_graph() — wires the StateGraph
│   └── session_store.py                # SessionStoreV2 (SQLite, separate DB file
│                                         # from V1's session_store.py)
└── data/                    # shared CSVs, sessions_v2.db
```

## Agent architecture

```
START → supervisor → (conditional: sales | technical | booking | end)
      sub-agent → supervisor → end   (supervisor's 2nd visit ends the turn)
```

- **Supervisor** (`supervisor.py`): classifies intent via LLM
  (`_llm_classify`) with a keyword-match fallback (`_keyword_classify`) if
  the LLM call fails or returns something invalid. Also extracts
  category/budget/rating filters from the message and carries forward
  `selected_category`/`filters` in state. A booking flow already in
  progress (`booking_state.step` in `selecting_product`,
  `collecting_details`, or `processing_payment`) forces `intent = "booking"`
  outright — free-text replies like "the second one" or a raw
  `payment_confirmed` signal can't be reliably reclassified out of context.
- **`_agent_responded`**: internal bookkeeping flag. A sub-agent sets it
  once it has produced the turn's reply; on the Supervisor's second visit
  (after the `sub-agent → supervisor` edge) it sees the flag and ends the
  turn instead of reclassifying the same message.
- **Sales / Technical agents** (`sales_agent.py`, `technical_agent.py`):
  both are thin wrappers around `common.run_retrieval_agent()` — same
  retrieval/synthesis flow, different system prompt. Technical Agent passes
  `reuse_existing_products=True` so a follow-up like "compare these" or "which
  has a better camera" reasons over the same `retrieved_products` from state
  instead of re-querying the retriever.
- **Booking Agent** (`booking_agent.py`): pure state machine, no LLM calls
  except optionally to phrase the final confirmation. Steps:
  1. `selecting_product` — only entered when more than one retrieved
     product is in play and none is selected yet; resolves the user's
     reply by list number, ordinal word, or unique name substring
  2. `collecting_details` — deterministic regex parsing of `name`,
     `address`, `phone`, `payment_method` from free text (labeled
     `key: value` pairs, or a bare 10-digit phone number with optional
     `+91`/`91` prefix)
  3. `validating` — checks the selected product has a name and a positive
     price
  4. `processing_payment` — **waits** for the frontend's payment page to
     send back `payment_confirmed` or `payment_failed` (see Frontend). On
     failure, resets to `collecting_details` and clears `payment_method`
     only, keeping name/address/phone the user already gave.
  5. `creating_order` → `confirmed` — builds the order record and phrases
     the confirmation (LLM if available, template fallback otherwise)

## RAG pipeline (`rag/retriever.py`)

```
query
  ↓
metadata filter (category / budget_min / budget_max / min_rating)
  applied BEFORE retrieval, on both paths below — never retrieve-then-filter
  ↓
Dense search (AstraDB native filter, K=20)   |   BM25 (pre-sliced corpus, K=20)
  ↓
Reciprocal Rank Fusion (RRF, k=60, merge size=30)
  ↓
Cross-encoder rerank (input=15) → top 4 (FINAL_TOP_N)
```

- Talks to AstraDB **directly via `astrapy`**, not LlamaIndex's
  `AstraDBVectorStore` wrapper — that wrapper's filter translation only
  supports equality, which can't express budget/rating range queries.
- BM25 runs over an in-memory corpus built by `ProductDataPipeline` (same
  source ingestion uses for AstraDB), pre-filtered by the same
  category/budget/rating predicate before scoring — the corpus subset
  differs per query, not a fixed global index.
- Results are cached in-process (`CACHE_SIZE=100`, LRU) keyed on
  `(query, category, min_rating, budget_min, budget_max)`.
- Category values are normalized (`laptops`/`Laptops`/`laptop` → `Laptop`)
  since ingestion stores singular category names but user-facing text is
  plural.

## Frontend structure (`frontend-astro/`)

```
src/
├── pages/
│   ├── index.astro           # landing page — category cards (hover wiggle,
│   │                            click scale-then-navigate animation)
│   ├── chat/[category].astro    # main chat UI; same-category refresh restores
│   │                             the session/transcript, switching category
│   │                             (or "New conversation") starts fresh;
│   │                             hosts the compare bar + product detail panel
│   │                             DOM (kept outside the message list so re-renders
│   │                             don't wipe them)
│   └── payment.astro              # mock payment page — math-challenge gate
│                                    (max 3 attempts), redirects back to
│                                    chat/[category] with ?payment=success|failed
├── layouts/Layout.astro         # shared shell; dark-mode toggle + pre-paint
│                                  script live here (re-themes via CSS var
│                                  overrides in global.css, no dark: variants
│                                  needed elsewhere)
├── lib/
│   ├── api.js                    # postChat / getSession / deleteSession
│   ├── session.js                  # sessionStorage session_id
│   ├── history.js                   # sessionStorage transcript cache (backend
│   │                                  doesn't return the rendered transcript,
│   │                                  only a state snapshot)
│   ├── categories.js                 # slug ↔ label map
│   └── chat-app.js                    # all chat UI logic: rendering, booking
│                                        form, budget quick-picks, product cards,
│                                        compare selection + comparison table,
│                                        detail panel, payment redirect handling
└── styles/global.css              # Tailwind v4 theme tokens + dark overrides
```

Notable frontend behaviors:
- **Product cards** → click opens a slide-in detail panel (parses bullet
  points out of the product's `content` field, since there's no dedicated
  `Details` field — see RAG pipeline notes on `rag/models.py`); each card
  also has a compare checkbox (max 3 selected, sticky "Compare (N)" button
  appears once 2+ are picked).
- **Compare** sends `"Compare these products: A vs B vs C"` to the
  Technical Agent through the normal `/chat` endpoint, then renders a
  client-side comparison table + a "we recommend" banner (highest rating
  wins, ties broken by lower price) above the LLM's text reply.
- **Booking form** collects name/address/phone/payment method (payment as
  3 buttons, not free text) in one step, then the flow leaves the chat
  entirely for `/payment`, a math-challenge (addition/subtraction, 1–20,
  never negative) gating a mocked payment confirmation.
- The first-turn Supervisor "clarify" message is intercepted client-side
  (exact string match) and replaced with category-specific budget
  quick-pick buttons instead of shown as raw text.

## Running locally

```bash
# Backend (from backend/)
uvicorn app_v2:app --host 0.0.0.0 --port 8000 --reload

# Frontend (from frontend-astro/)
npm run dev
```

`frontend-astro/src/config.js` points at `http://localhost:8000` by
default; override with `PUBLIC_API_BASE_URL` if the backend runs elsewhere.

## Environment variables (`backend/.env`)

```
GROQ_API_KEY=
ASTRA_DB_API_ENDPOINT=
ASTRA_DB_APPLICATION_TOKEN=
ASTRA_DB_KEYSPACE=
ASTRA_DB_COLLECTION=

# External catalog-fallback APIs (rag/api_fallback.py)
MOBILE_API_KEY=
TECHSPECS_API_ID=
TECHSPECS_API_KEY=

# LangSmith tracing (optional)
LANGCHAIN_TRACING_V2=
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=
```

(`OPENAI_API_KEY` also exists in `.env` from earlier experimentation but
V2's live path — Groq LLM + local sentence-transformers embeddings — does
not require it.)

## Do NOT touch

- `backend/flipkart/` — V1 backend, untouched parallel implementation
- `frontend/` — V1 frontend (React + Vite), untouched parallel implementation

These are kept for reference only; V2 is a ground-up rebuild, not an
in-place edit.

## Decisions worth knowing

- **Dropped `langchain-astradb`** from the V2 dependency set. It pins
  `astrapy<2.0`, which conflicts with `llama-index-vector-stores-astra-db`
  (wants `astrapy~=1.5`+ compatible with 2.x) — this exact collision broke
  V1 previously. V2 talks to AstraDB with `astrapy` directly instead of
  going through either library's vector-store wrapper.
- **Pre-retrieval metadata filtering** is non-negotiable: category/budget/
  rating filters are applied before both the dense and BM25 searches run,
  never as a post-hoc filter over an unfiltered result set. This was a
  known failure mode in an earlier attempt at this pipeline.
- **Booking Agent is deterministic, not LLM-driven.** Field extraction,
  step transitions, and validation are all regex/state-machine logic. The
  only optional LLM call is phrasing the final confirmation message, with
  a template fallback if that call fails or no LLM is configured.
- **Mock payment is a math challenge, not an auto-mock gateway.** Earlier
  in V2's life the Booking Agent auto-resolved payment success/failure
  from the payment method string (e.g. "decline" in the name = failure).
  That's gone — `processing_payment` now blocks until the frontend's
  `/payment` page (a simple arithmetic challenge, 3 attempts) sends back an
  explicit `payment_confirmed`/`payment_failed` signal over `/chat`.
- **Session state forks per category, not per page load.** Switching to a
  different category (tracked via `flipkart_last_category` in
  sessionStorage) or clicking "New conversation" starts a fresh session_id
  and clears local history — conversations never carry state across
  categories. Refreshing the same category page keeps the session and
  restores the transcript from sessionStorage.
