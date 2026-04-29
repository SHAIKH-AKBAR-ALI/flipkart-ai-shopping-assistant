import json

from langchain_astradb import AstraDBVectorStore
from langchain_core.documents import Document
from langchain_groq import ChatGroq

from flipkart import config
from flipkart.retriever import HybridRetriever
from flipkart.session_store import SessionStore

_SYSTEM_PROMPT = """You are a smart Flipkart shopping assistant. Help users find the best products based on real customer reviews and ratings.
Always base recommendations on retrieved reviews.
Mention specific pros/cons from actual reviews.
Show rating and price when recommending.
For comparisons make a clean markdown table.
Be concise and structured.
Always end with 3 suggested follow-up questions.

Always respond in this exact JSON format (no markdown, raw JSON only):
{
  "answer": "your response here",
  "products": [{"name": "", "price": "", "rating": "", "summary": ""}],
  "follow_ups": ["q1", "q2", "q3"],
  "intent": "recommend|compare|explain|filter|general",
  "rag_trace": {
    "query_variants": [],
    "docs_retrieved": 0,
    "docs_after_rerank": 0,
    "retrieval_time": 0
  }
}"""


def _format_docs(docs: list[Document]) -> str:
    parts = []
    for i, doc in enumerate(docs, start=1):
        m = doc.metadata
        parts.append(
            f"[{i}] {m.get('product_name', 'Unknown')} | "
            f"Rating: {m.get('rating', 'N/A')} | "
            f"Price: ₹{m.get('price', 'N/A')} | "
            f"Category: {m.get('category', 'N/A')}\n"
            f"Review: {doc.page_content}"
        )
    return "\n\n".join(parts)


def _safe_parse(raw: str, meta) -> dict:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
    except Exception:
        result = {
            "answer": raw,
            "products": [],
            "follow_ups": [],
            "intent": "general",
        }

    result["rag_trace"] = {
        "query_variants": meta.query_variants,
        "docs_retrieved": meta.docs_retrieved,
        "docs_after_rerank": meta.docs_after_rerank,
        "retrieval_time": round(meta.retrieval_time, 3),
    }
    return result


class RAGChain:
    def __init__(self, vector_store: AstraDBVectorStore, documents: list[Document]):
        self.retriever = HybridRetriever(vector_store, documents)
        self.session_store = SessionStore()
        self.llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )

    def invoke(self, query: str, session_id: str) -> dict:
        history = self.session_store.get_last_n_turns(session_id, n=config.HISTORY_WINDOW)
        docs, meta = self.retriever.retrieve(query)
        context = _format_docs(docs)

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for msg in history:
            messages.append(msg)
        messages.append({
            "role": "user",
            "content": f"Retrieved product reviews:\n{context}\n\nUser query: {query}",
        })

        raw = self.llm.invoke(messages).content

        self.session_store.save_message(session_id, "user", query)
        self.session_store.save_message(session_id, "assistant", raw)
        self.session_store.summarize_old_messages(session_id)

        return _safe_parse(raw, meta)
