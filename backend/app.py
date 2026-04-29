import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from flipkart.agent import FlipkartAgent
from flipkart.data_converter import load_documents
from flipkart.data_ingestion import DataIngestor
from flipkart.evaluator import RAGEvaluator
from flipkart.session_store import SessionStore

# Maps UI category ids → internal category names used in metadata
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


# ── Startup / shutdown ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lightweight state only — expensive init is deferred to first request
    app.state.agent = None
    app.state.evaluator = None
    app.state.session_store = SessionStore()
    app.state.chat_count = 0
    app.state.category_counts = Counter()

    print("Startup complete. Agent will be initialized on first request.")
    yield


# ── Lazy initializer ───────────────────────────────────────────────────────────

def _get_or_init_agent() -> FlipkartAgent:
    """Initialize the agent, vector store, and evaluator on first use.

    Subsequent calls return the already-cached instances from app.state,
    so the expensive embedding model load and AstraDB connection only
    happen once — on the first real API request, not during startup.
    """
    if app.state.agent is None:
        print("Lazy init: loading documents and initializing agent...")
        documents = load_documents()
        vector_store = DataIngestor().ingest(load_existing=True)

        app.state.agent = FlipkartAgent(vector_store=vector_store, documents=documents)
        app.state.evaluator = RAGEvaluator()
        app.state.category_counts = Counter(doc.metadata["category"] for doc in documents)

        print(f"Lazy init complete. {len(documents)} docs loaded for BM25.")

    return app.state.agent


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
    """Scheduled as a FastAPI background task — runs after response is sent."""
    asyncio.run(evaluator.evaluate_async(query, answer, contexts))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/categories")
def categories():
    _get_or_init_agent()
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
    agent: FlipkartAgent = _get_or_init_agent()
    evaluator: RAGEvaluator = app.state.evaluator

    app.state.chat_count += 1
    run_ragas = (app.state.chat_count % 5 == 0)

    category = _resolve_category(req.category)
    filters = req.filters.model_dump() if req.filters else None
    
    response = agent.run(
        query=req.query, 
        session_id=req.session_id, 
        category=category,
        filters=filters
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
    agent: FlipkartAgent = _get_or_init_agent()
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
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
