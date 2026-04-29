import asyncio
import logging
import os
from collections import Counter
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from flipkart.agent import FlipkartAgent
from flipkart.data_converter import load_documents
from flipkart.data_ingestion import DataIngestor
from flipkart.evaluator import RAGEvaluator
from flipkart.session_store import SessionStore

logger = logging.getLogger(__name__)

_CATEGORY_ID_MAP = {
    "laptop": "Laptop",
    "mobile": "Mobile",
    "tv": "TV",
    "refrigerator": "Refrigerator",
    "smart_watch": "Smart Watch",
    "washing_machine": "Washing Machine",
}


def _resolve_category(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return _CATEGORY_ID_MAP.get(raw.lower(), raw)


# ── Background initializer ─────────────────────────────────────────────────────

async def _initialize_app(app: FastAPI) -> None:
    """Run heavy init in thread pool so the server can serve /health immediately."""
    try:
        loop = asyncio.get_event_loop()

        logger.info("Loading CSV documents...")
        documents = await loop.run_in_executor(None, load_documents)

        logger.info("Connecting to AstraDB vector store...")
        vector_store = await loop.run_in_executor(
            None, lambda: DataIngestor().ingest(load_existing=True)
        )

        logger.info("Building FlipkartAgent (loads embeddings + reranker)...")
        agent = await loop.run_in_executor(
            None, lambda: FlipkartAgent(vector_store=vector_store, documents=documents)
        )

        app.state.agent = agent
        app.state.evaluator = RAGEvaluator()
        app.state.session_store = SessionStore()
        app.state.category_counts = Counter(doc.metadata["category"] for doc in documents)
        app.state.ready = True

        logger.info(f"Startup complete. {len(documents)} docs loaded for BM25.")
    except Exception:
        logger.exception("Background initialization failed.")
        app.state.ready = False


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed state immediately so every endpoint has safe attribute access
    app.state.ready = False
    app.state.agent = None
    app.state.evaluator = None
    app.state.session_store = None
    app.state.chat_count = 0
    app.state.category_counts = Counter()

    # Heavy init runs in background — server accepts /health right away
    asyncio.create_task(_initialize_app(app))

    yield


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Flipkart RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)


# ── Request/Response models ────────────────────────────────────────────────────

class FiltersModel(BaseModel):
    min_rating: Optional[float] = None
    category: Optional[str] = None


class ChatRequest(BaseModel):
    query: str
    session_id: str
    category: Optional[str] = None
    filters: Optional[FiltersModel] = None


class AnalyzeRequest(BaseModel):
    product_name: str
    category: str
    session_id: str


# ── Background RAGAS task ──────────────────────────────────────────────────────

def _fire_ragas(evaluator: RAGEvaluator, query: str, answer: str, contexts: list[str]):
    asyncio.run(evaluator.evaluate_async(query, answer, contexts))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "ready": app.state.ready}


@app.get("/categories")
def categories():
    if not app.state.ready:
        return {"categories": []}
    counts = app.state.category_counts
    return {
        "categories": [
            {"id": "laptop",           "name": "Laptops",          "icon": "💻", "count": counts.get("Laptop", 0)},
            {"id": "mobile",           "name": "Mobiles",          "icon": "📱", "count": counts.get("Mobile", 0)},
            {"id": "tv",               "name": "Televisions",      "icon": "📺", "count": counts.get("TV", 0)},
            {"id": "refrigerator",     "name": "Refrigerators",    "icon": "🧊", "count": counts.get("Refrigerator", 0)},
            {"id": "smart_watch",      "name": "Smart Watches",    "icon": "⌚", "count": counts.get("Smart Watch", 0)},
            {"id": "washing_machine",  "name": "Washing Machines", "icon": "🫧", "count": counts.get("Washing Machine", 0)},
        ]
    }


@app.post("/chat")
async def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    if not app.state.ready:
        raise HTTPException(status_code=503, detail="Service is initializing. Retry in ~60 seconds.")

    agent: FlipkartAgent = app.state.agent
    evaluator: RAGEvaluator = app.state.evaluator

    app.state.chat_count += 1
    run_ragas = (app.state.chat_count % 5 == 0)

    category = _resolve_category(req.category)
    filters = req.filters.model_dump() if req.filters else None

    response = agent.run(
        query=req.query,
        session_id=req.session_id,
        category=category,
        filters=filters,
    )

    if "rag_trace" not in response:
        response["rag_trace"] = {}
    response["rag_trace"]["ragas"] = {}

    if run_ragas:
        contexts = agent.get_last_contexts()
        answer = response.get("answer", "")
        background_tasks.add_task(_fire_ragas, evaluator, req.query, answer, contexts)

    return response


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if not app.state.ready:
        raise HTTPException(status_code=503, detail="Service is initializing. Retry in ~60 seconds.")
    agent: FlipkartAgent = app.state.agent
    category = _resolve_category(req.category)
    result = agent.analyze_product(product_name=req.product_name, category=category or req.category)
    return result


@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    app.state.session_store.clear_session(session_id)
    return {"cleared": True}


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
