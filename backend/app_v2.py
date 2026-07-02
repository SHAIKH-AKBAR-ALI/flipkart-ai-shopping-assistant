import asyncio
import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_GRAPH_TIMEOUT = 30

_INTENT_TO_AGENT = {
    "sales": "Sales Agent",
    "technical": "Technical Agent",
    "booking": "Booking Agent",
    "clarify": "Supervisor",
}


# ── Background initializer ─────────────────────────────────────────────────────

async def _initialize_app(app: FastAPI) -> None:
    """Heavy init in thread pool. NEVER raises — failures stored on app.state.init_error.
    Ported from V1's app.py pattern (backend/app.py::_initialize_app)."""
    try:
        logger.info("Background init (v2): starting.")

        from agents.graph import build_graph
        from agents.session_store import SessionStoreV2
        from rag.retriever import HybridRetriever

        loop = asyncio.get_event_loop()

        try:
            logger.info("Background init (v2): building HybridRetriever (embeddings + BM25 corpus)...")
            retriever = await loop.run_in_executor(None, HybridRetriever)
        except Exception as e:
            app.state.init_error = f"HybridRetriever failed: {e}"
            logger.exception("HybridRetriever failed.")
            return

        try:
            logger.info("Background init (v2): compiling LangGraph multi-agent graph...")
            graph = await loop.run_in_executor(None, lambda: build_graph(retriever=retriever))
        except Exception as e:
            app.state.init_error = f"build_graph failed: {e}"
            logger.exception("build_graph failed.")
            return

        try:
            app.state.retriever = retriever
            app.state.graph = graph
            app.state.session_store = SessionStoreV2()
            app.state.ready = True
            logger.info("Background init (v2): complete.")
        except Exception as e:
            app.state.init_error = f"final wiring failed: {e}"
            logger.exception("Final wiring failed.")

    except Exception as e:
        try:
            app.state.init_error = f"unexpected: {e}\n{traceback.format_exc()}"
        except Exception:
            pass
        logger.exception("Background init (v2): unexpected top-level exception.")


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    app.state.init_error = None
    app.state.retriever = None
    app.state.graph = None
    app.state.session_store = None

    try:
        asyncio.create_task(_initialize_app(app))
    except Exception:
        logger.exception("Failed to schedule background init task.")

    yield


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Flipkart RAG API v2 (multi-agent)", lifespan=lifespan)

# ALLOWED_ORIGINS: comma-separated env allowlist; local Astro dev server default.
_allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or ["http://localhost:4321"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    # Credentials only with an explicit allowlist — never with a wildcard.
    allow_credentials="*" not in _allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handlers (ported from V1's app.py) ────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": f"HTTP_{exc.status_code}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "code": "VALIDATION_ERROR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    logger.exception("Unhandled server error occurred.")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "code": "INTERNAL_SERVER_ERROR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ── Request/Response models ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Always returns 200. Reads no state — safe even if lifespan never ran."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe — reflects whether the graph/retriever finished initializing."""
    return {
        "ready": getattr(app.state, "ready", False),
        "init_error": getattr(app.state, "init_error", None),
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service is initializing. Retry in ~60 seconds.")

    if not req.session_id or not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id must not be empty.")
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty.")

    from langchain_core.messages import HumanMessage

    store = app.state.session_store
    graph = app.state.graph

    state = await asyncio.to_thread(store.get_state, req.session_id)
    state["messages"] = state["messages"] + [HumanMessage(content=req.message)]
    state["_agent_responded"] = False

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(graph.invoke, state), timeout=_GRAPH_TIMEOUT
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=500, detail=f"Agent graph timed out after {_GRAPH_TIMEOUT}s."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Graph invocation failed.")
        raise HTTPException(status_code=500, detail=f"Agent graph failed: {e}")

    await asyncio.to_thread(store.save_state, req.session_id, result)

    messages = result.get("messages", [])
    last_ai = messages[-1].content if messages else ""
    intent = result.get("intent")

    return {
        "message": last_ai,
        "intent": intent,
        "retrieved_products": result.get("retrieved_products", []),
        "agent_used": _INTENT_TO_AGENT.get(intent, "unknown"),
    }


@app.get("/session/{session_id}")
def get_session(session_id: str):
    store = getattr(app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session store not yet initialized.")

    state = store.get_state(session_id)
    return {
        "session_id": session_id,
        "exists": store.exists(session_id),
        "selected_category": state.get("selected_category"),
        "selected_product": state.get("selected_product"),
        "filters": state.get("filters"),
        "retrieved_products": state.get("retrieved_products"),
        "booking_state": state.get("booking_state"),
        "message_count": len(state.get("messages", [])),
    }


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

    port = int(os.environ.get("PORT", os.environ.get("PORT_V2", 8000)))
    uvicorn.run("app_v2:app", host="0.0.0.0", port=port, reload=True)
