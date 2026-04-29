import asyncio
import logging
import os
import traceback
from collections import Counter
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
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
    """Heavy init in thread pool. NEVER raises — failures stored on app.state.init_error."""
    try:
        logger.info("Background init: starting.")

        # Imports inside the task so a missing dep cannot crash module load
        from flipkart.agent import FlipkartAgent
        from flipkart.data_converter import load_documents
        from flipkart.data_ingestion import DataIngestor
        from flipkart.evaluator import RAGEvaluator
        from flipkart.session_store import SessionStore

        loop = asyncio.get_event_loop()

        try:
            logger.info("Background init: loading CSV documents...")
            documents = await loop.run_in_executor(None, load_documents)
        except Exception as e:
            app.state.init_error = f"load_documents failed: {e}"
            logger.exception("load_documents failed.")
            return

        try:
            logger.info("Background init: connecting to AstraDB vector store...")
            vector_store = await loop.run_in_executor(
                None, lambda: DataIngestor().ingest(load_existing=True)
            )
        except Exception as e:
            app.state.init_error = f"DataIngestor failed: {e}"
            logger.exception("DataIngestor failed.")
            return

        try:
            logger.info("Background init: building FlipkartAgent (embeddings + reranker)...")
            agent = await loop.run_in_executor(
                None, lambda: FlipkartAgent(vector_store=vector_store, documents=documents)
            )
        except Exception as e:
            app.state.init_error = f"FlipkartAgent failed: {e}"
            logger.exception("FlipkartAgent failed.")
            return

        try:
            app.state.agent = agent
            app.state.evaluator = RAGEvaluator()
            app.state.session_store = SessionStore()
            app.state.category_counts = Counter(doc.metadata["category"] for doc in documents)
            app.state.ready = True
            logger.info(f"Background init: complete. {len(documents)} docs loaded for BM25.")
        except Exception as e:
            app.state.init_error = f"final wiring failed: {e}"
            logger.exception("Final wiring failed.")

    except Exception as e:
        # Last-ditch catch — must never propagate to event loop
        try:
            app.state.init_error = f"unexpected: {e}\n{traceback.format_exc()}"
        except Exception:
            pass
        logger.exception("Background init: unexpected top-level exception.")


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed state up front so every endpoint has safe attribute access even if init crashes
    app.state.ready = False
    app.state.init_error = None
    app.state.agent = None
    app.state.evaluator = None
    app.state.session_store = None
    app.state.chat_count = 0
    app.state.category_counts = Counter()

    try:
        asyncio.create_task(_initialize_app(app))
    except Exception:
        logger.exception("Failed to schedule background init task.")

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

def _fire_ragas(evaluator, query: str, answer: str, contexts: list[str]):
    try:
        asyncio.run(evaluator.evaluate_async(query, answer, contexts))
    except Exception:
        logger.exception("RAGAS background task failed.")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Always returns 200. Reads no state — safe even if lifespan never ran."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe — reflects whether the agent has finished initializing."""
    return {
        "ready": getattr(app.state, "ready", False),
        "init_error": getattr(app.state, "init_error", None),
    }


@app.get("/categories")
def categories():
    if not getattr(app.state, "ready", False):
        return {"categories": []}
    counts = getattr(app.state, "category_counts", Counter())
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
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service is initializing. Retry in ~60 seconds.")

    agent = app.state.agent
    evaluator = app.state.evaluator

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
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service is initializing. Retry in ~60 seconds.")
    agent = app.state.agent
    category = _resolve_category(req.category)
    result = agent.analyze_product(product_name=req.product_name, category=category or req.category)
    return result


@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    store = getattr(app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session store not yet initialized.")
    store.clear_session(session_id)
    return {"cleared": True}


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
