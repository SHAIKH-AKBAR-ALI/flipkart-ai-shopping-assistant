# CHECKLIST.md — Flipkart AI Shopping Assistant V2

Project Status: 🟡 In Progress

---

## Phase 0 — Foundation Reset

Status: ✅ Done

- [x] Remove `langchain-astradb` from V2 environment
- [x] Pin `astrapy` to version compatible with `llama-index-vector-stores-astra-db`
- [x] Run `pip check` — zero conflicts
- [x] Create fresh AstraDB collection (old one is DNS-dead/deprovisioned)
- [x] Update `.env` with new collection details
- [x] Git init / commit clean starting point

Notes: committed as `66d84d2`.

---

## Phase 1 — RAG Core

Status: ✅ Done

- [x] Reuse/adapt `rag/ingestion.py` for new AstraDB collection
- [x] Implement `EmbeddingManager` fully
- [x] Run ingestion end-to-end — confirm documents actually land in AstraDB (not just built in memory)
- [x] Implement `HybridRetriever`:
  - [x] Dense search (AstraDB, native metadata filter — category/budget/rating applied pre-retrieval)
  - [x] BM25 (in-memory, pre-sliced by same filters before scoring)
  - [x] RRF merge
  - [x] Cross-encoder rerank → top 4
- [x] Verify retrieval standalone with a test script (3-5 sample queries, print ranked results) — before touching agents
- [x] Git commit

Notes: committed as `ffb53e0`.

---

## Phase 2 — Multi-Agent LangGraph

Status: ✅ Done

- [x] Define `AgentState` (TypedDict)
- [x] Supervisor Agent — intent routing (LLM-based + keyword fallback), shared state ownership
- [x] Sales Agent — pricing/EMI/offers, uses `HybridRetriever`
- [x] Technical Agent — specs/comparison/pros-cons, uses `HybridRetriever`
- [x] Booking Confirmation Agent — deterministic state machine, mocked payment step
- [x] Wire graph: Supervisor → sub-agents → back to Supervisor per turn
- [x] Test each agent independently with sample conversations
- [x] Git commit

Notes: committed as `e687a86`.

---

## Phase 3 — FastAPI Backend Integration

Status: ✅ Done

- [x] Wire multi-agent graph into `app_v2.py` endpoints (new V2 entrypoint — `app.py` stays V1-only, untouched)
- [x] Session memory (reuse V1's `session_store.py` pattern)
- [x] `/chat`, `/analyze`, `/health`, `/session/{id}` endpoints
- [x] End-to-end test: real query → Supervisor → agent → response
- [x] Git commit

Notes: committed as `25e6506`. Run with `uvicorn app_v2:app`, not `app:app` — CLAUDE.md command block still says `app:app`, needs correcting.

---

## Phase 4 — Astro Frontend

Status: ✅ Done

- [x] Landing page
- [x] Sidebar RAG chatbot UI (category buttons, chat window)
- [x] Booking flow UI (collect details → confirmation)
- [x] Connect to backend API
- [x] Git commit

Notes: Full E2E walkthrough run via headless Playwright against live backend (`app_v2:app`, real AstraDB + Groq) — homepage → category select → sales query (product cards) → technical follow-up → booking form → confirmed order → refresh (session + chat history persist via `sessionStorage`). `npm run build` succeeds (7 static pages). Zero console errors.

Bug found + fixed during verification: `app_v2.py` never called `load_dotenv()`, so `backend/.env` creds were never loaded into `os.environ` — `/ready` failed with "Missing AstraDB connection variables" even with valid creds present. Fixed by adding `load_dotenv()` at module load.

---

## Phase 5 — Integration, Testing & Polish

Status: ⏳ Pending

- [ ] Full end-to-end testing (chat → booking → confirmation)
- [ ] Bug fixes
- [ ] Rename/rebrand
- [ ] Deployment
- [ ] Final README update

Notes:

---

## Current Phase

Phase: 5 — Integration, Testing & Polish
Status: ⏳ Pending

---

## Completed Phases

- Phase 0 — Foundation Reset (`66d84d2`)
- Phase 1 — RAG Core (`ffb53e0`)
- Phase 2 — Multi-Agent LangGraph (`e687a86`)
- Phase 3 — FastAPI Backend Integration (`25e6506`)
- Phase 4 — Astro Frontend

---

## Known Issues

- Old AstraDB endpoint is DNS-dead — must provision new collection in Phase 0
- Prior V2 attempt (`rag/retriever.py`, `rag/query_engine.py`) were stubs only (`pass`/`return []`) — not reusable beyond `ingestion.py`

---

## Architecture Decisions Log

- Frontend: Astro (not React) — full rebuild
- RAG: LlamaIndex replacing LangChain entirely for retrieval layer
- Metadata filtering: pre-retrieval on both dense + BM25 paths (not post-merge)
- Agents: Supervisor + multi-agent (Sales/Technical/Booking), not single agent
- Booking: deterministic, no LLM, mocked payment
- Routing: back to Supervisor each turn, not straight to END