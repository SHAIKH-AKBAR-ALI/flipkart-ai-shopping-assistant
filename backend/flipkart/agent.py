import json
import threading
from typing import Optional, Any

from langchain_astradb import AstraDBVectorStore
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from flipkart import config
from flipkart.retriever import HybridRetriever
from flipkart.session_store import SessionStore

_AGENT_TIMEOUT = 30

# ── Keyword routing ────────────────────────────────────────────────────────────

_CATEGORY_KEYWORDS = {
    "Laptop": ["laptop", "computer", "notebook"],
    "Mobile": ["phone", "mobile", "smartphone"],
    "TV": ["tv", "television", "screen"],
    "Refrigerator": ["fridge", "refrigerator"],
    "Smart Watch": ["watch", "smartwatch"],
    "Washing Machine": ["washing", "washer"],
}

_CATEGORY_NODE_MAP = {
    "Laptop": "laptop_specialist",
    "Mobile": "mobile_specialist",
    "TV": "tv_specialist",
    "Refrigerator": "refrigerator_specialist",
    "Smart Watch": "smart_watch_specialist",
    "Washing Machine": "washing_machine_specialist",
}


def _detect_category(query: str) -> str:
    q = query.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return category
    return "all"


# ── Specialist prompts ─────────────────────────────────────────────────────────

_SPECIALIST_PROMPTS = {
    "Laptop": (
        "You are an expert Laptop shopping advisor with deep knowledge of Laptop specifications.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them based on specifications, then recommend the best fit for the user query.\n"
        "Prioritization Criteria: processor > RAM > storage > display > battery.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"I found 3 laptops. The ASUS VivoBook is best for your budget due to its Ryzen 5 processor...","products":[{"name":"ASUS VivoBook 15","price":"₹45,990","rating":"4.3","summary":"Ryzen 5, 8GB RAM, 512GB SSD"}],"follow_ups":["Best for gaming?","Dell alternative?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
    "Mobile": (
        "You are an expert Mobile shopping advisor with deep knowledge of Mobile specifications.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them based on specifications, then recommend the best fit for the user query.\n"
        "Prioritization Criteria: camera > battery > processor > display > RAM.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"I found 2 smartphones. The Samsung A54 offers the best camera in this range...","products":[{"name":"Samsung Galaxy A54","price":"₹35,499","rating":"4.4","summary":"50MP Triple Cam, 5000mAh Battery"}],"follow_ups":["Best for gaming?","Stock Android option?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
    "TV": (
        "You are an expert TV shopping advisor with deep knowledge of TV specifications.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them based on specifications, then recommend the best fit for the user query.\n"
        "Prioritization Criteria: display tech > resolution > smart OS > sound.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"The Sony Bravia is the top pick for its OLED display and 4K resolution...","products":[{"name":"Sony Bravia OLED","price":"₹1,24,990","rating":"4.8","summary":"4K OLED, Google TV, 30W Sound"}],"follow_ups":["Is there a QLED option?","Best for PS5?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
    "Refrigerator": (
        "You are an expert Refrigerator shopping advisor with deep knowledge of Refrigerator specifications.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them based on specifications, then recommend the best fit for the user query.\n"
        "Prioritization Criteria: capacity > energy rating > cooling tech.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"The LG Frost-Free fridge is ideal for your family size with its 3-star rating...","products":[{"name":"LG 260L 3-Star","price":"₹24,990","rating":"4.2","summary":"Frost-Free, Smart Inverter"}],"follow_ups":["Is there a 5-star option?","Samsung alternative?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
    "Smart Watch": (
        "You are an expert Smart Watch shopping advisor with deep knowledge of Smart Watch specifications.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them based on specifications, then recommend the best fit for the user query.\n"
        "Prioritization Criteria: health sensors > battery > display.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"The Apple Watch Series 9 is the gold standard for health tracking...","products":[{"name":"Apple Watch Series 9","price":"₹41,900","rating":"4.7","summary":"ECG, Blood Oxygen, Always-on Display"}],"follow_ups":["Best budget option?","Longest battery life?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
    "Washing Machine": (
        "You are an expert Washing Machine shopping advisor with deep knowledge of Washing Machine specifications.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them based on specifications, then recommend the best fit for the user query.\n"
        "Prioritization Criteria: capacity > energy efficiency > wash programs.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"This IFB Front Load machine is perfect for large families with its 8kg capacity...","products":[{"name":"IFB 8kg Front Load","price":"₹32,490","rating":"4.5","summary":"5-Star, 14 Wash Programs"}],"follow_ups":["Is Top Load cheaper?","Samsung alternative?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
    "all": (
        "You are an expert Shopping Advisor with deep knowledge across multiple product categories.\n"
        "Chain of Thought: First analyze the retrieved products, then compare them, then recommend the best options for the user.\n"
        "Negative Instructions: Never recommend products not found in the retrieved context. Never make up specifications.\n"
        "Confidence: If retrieved products don't match the query well, say so honestly.\n"
        "Example Format:\n"
        '{"answer":"I found several interesting products across categories. Here are the top picks...","products":[{"name":"Product Name","price":"₹Price","rating":"4.5","summary":"Key Specs"}],"follow_ups":["More budget options?","Compare brands?"],"intent":"recommend","rag_trace":{}}\n'
        "Return raw JSON only (no markdown)."
    ),
}

_SPECIALIST_FOLLOW_UPS = {
    "Laptop": ["What's the best laptop under ₹50,000?", "Which laptop has the longest battery life?", "Which laptop is best for gaming?"],
    "Mobile": ["Which phone has the best camera under ₹30,000?", "What's the best 5G phone?", "Which phone has the longest battery?"],
    "TV": ["Which TV is best for gaming?", "What's the best 4K TV under ₹40,000?", "Which TV has the best sound quality?"],
    "Refrigerator": ["Which fridge is most energy efficient?", "What's the best double door fridge?", "Which brand has the best after-sales service?"],
    "Smart Watch": ["Which smartwatch has the best health tracking?", "What's the best smartwatch under ₹5,000?", "Which watch has longest battery life?"],
    "Washing Machine": ["Which is better: front load or top load?", "What's the best washing machine under ₹20,000?", "Which brand is most reliable?"],
    "all": ["Can you recommend products under a specific budget?", "Which brand has the best ratings?", "What are the top rated products right now?"],
}

_ONBOARDING_QUESTIONS = {
    "Mobile": "What's your budget range and main use case — gaming, camera, or everyday use?",
    "Laptop": "What's your budget and primary use — coding, gaming, office work, or college?",
    "TV": "What screen size are you looking for and is smart TV features important to you?",
    "Refrigerator": "How many family members and do you prefer single or double door?",
    "Smart Watch": "Are you focused on fitness tracking, notifications, or both?",
    "Washing Machine": "What's your family size and do you prefer front load or top load?",
}

_ANALYSIS_PROMPTS = {
    "Laptop": (
        "You are an expert Laptop reviewer with deep technical knowledge of specifications.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Evaluation Priorities: processor > RAM > storage > display > battery.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
    "Mobile": (
        "You are an expert Mobile phone reviewer with deep technical knowledge of hardware and software.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Evaluation Priorities: camera > battery > processor > display > RAM.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
    "TV": (
        "You are an expert TV reviewer with deep knowledge of display technologies and smart features.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Evaluation Priorities: display tech > resolution > smart OS > sound.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
    "Refrigerator": (
        "You are an expert Refrigerator reviewer with deep knowledge of cooling tech and energy efficiency.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Evaluation Priorities: capacity > energy rating > cooling tech.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
    "Smart Watch": (
        "You are an expert Smart Watch reviewer with deep knowledge of health sensors and wearables.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Evaluation Priorities: health sensors > battery > display.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
    "Washing Machine": (
        "You are an expert Washing Machine reviewer with deep knowledge of laundry technology and efficiency.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Evaluation Priorities: capacity > energy efficiency > wash programs.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
    "all": (
        "You are an expert Product Reviewer with deep knowledge across multiple categories.\n"
        "Chain of Thought: Analyze the target product's specs, evaluate them against market standards and price, then provide a critical review.\n"
        "Negative Instructions: Never make up specifications. Do not hallucinate pros or cons not supported by data.\n"
        "Confidence: If product data is incomplete, state 'Insufficient data' in the specs summary.\n"
        "Return raw JSON only (no markdown):\n"
        '{"value_score":8.5,"pros":["pro1","pro2","pro3"],"cons":["con1","con2"],"who_should_buy":"...","who_should_avoid":"...","better_alternatives":[{"name":"","price":0,"rating":0.0,"reason":""}],"verdict":"...","specs_summary":"..."}'
    ),
}


# ── LangGraph state ────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    query: str
    history_messages: list
    category: str
    forced_category: Optional[str]
    filters: Optional[dict]
    response: dict
    last_docs: list
    last_meta: Any


# ── Doc formatter ──────────────────────────────────────────────────────────────

def _format_docs(docs: list[Document]) -> str:
    lines = [f"Found {len(docs)} product(s)."]
    for doc in docs:
        m = doc.metadata
        lines.append(
            f"- {m.get('product_name')} | Brand: {m.get('brand')} | "
            f"Rating: {m.get('rating')} | Price: ₹{m.get('price')} | "
            f"Category: {m.get('category')}\n  Specs: {doc.page_content[:400]}"
        )
    return "\n".join(lines)


def _parse_response(raw: str) -> dict:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return {"answer": raw, "products": [], "follow_ups": [], "intent": "general", "rag_trace": {}}


# ── Agent class ────────────────────────────────────────────────────────────────

class FlipkartAgent:
    def __init__(self, vector_store: AstraDBVectorStore, documents: list[Document]):
        self.session_store = SessionStore()
        self._retriever = HybridRetriever(vector_store, documents)
        self._llm = ChatGroq(
            model=config.LLM_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
        self._last_state: dict = {}
        self._graph = self._build_graph()

    def _build_graph(self):
        retriever = self._retriever
        llm = self._llm

        def router_node(state: AgentState) -> AgentState:
            if state.get("forced_category"):
                return {**state, "category": state["forced_category"]}
            category = _detect_category(state["query"])
            return {**state, "category": category}

        def route_to_specialist(state: AgentState) -> str:
            return _CATEGORY_NODE_MAP.get(state["category"], "general_specialist")

        def make_specialist(category_key: str):
            def specialist_node(state: AgentState) -> AgentState:
                query = state["query"]
                category = state["category"]
                system_prompt = _SPECIALIST_PROMPTS.get(category_key, _SPECIALIST_PROMPTS["all"])

                retrieval_filters = {"category": category} if category != "all" else {}
                if state.get("filters"):
                    retrieval_filters.update(state["filters"])

                docs, meta = retriever.retrieve(query, filters=retrieval_filters)

                context = _format_docs(docs) if docs else "No products found in database."
                messages = [
                    SystemMessage(content=system_prompt),
                    *state["history_messages"],
                    HumanMessage(content=f"Products:\n{context}\n\nQuery: {query}"),
                ]
                raw = llm.invoke(messages).content
                parsed = _parse_response(raw)

                if meta:
                    parsed["rag_trace"] = {
                        "query_variants": meta.query_variants,
                        "docs_retrieved": meta.docs_retrieved,
                        "docs_after_rerank": meta.docs_after_rerank,
                        "retrieval_time": meta.retrieval_time,
                        "category": category,
                    }

                if not parsed.get("follow_ups"):
                    parsed["follow_ups"] = _SPECIALIST_FOLLOW_UPS.get(category_key, _SPECIALIST_FOLLOW_UPS["all"])

                return {**state, "response": parsed, "last_docs": docs, "last_meta": meta}

            return specialist_node

        graph = StateGraph(AgentState)
        graph.add_node("router", router_node)
        graph.add_node("laptop_specialist", make_specialist("Laptop"))
        graph.add_node("mobile_specialist", make_specialist("Mobile"))
        graph.add_node("tv_specialist", make_specialist("TV"))
        graph.add_node("refrigerator_specialist", make_specialist("Refrigerator"))
        graph.add_node("smart_watch_specialist", make_specialist("Smart Watch"))
        graph.add_node("washing_machine_specialist", make_specialist("Washing Machine"))
        graph.add_node("general_specialist", make_specialist("all"))

        graph.add_edge(START, "router")
        graph.add_conditional_edges(
            "router",
            route_to_specialist,
            {
                "laptop_specialist": "laptop_specialist",
                "mobile_specialist": "mobile_specialist",
                "tv_specialist": "tv_specialist",
                "refrigerator_specialist": "refrigerator_specialist",
                "smart_watch_specialist": "smart_watch_specialist",
                "washing_machine_specialist": "washing_machine_specialist",
                "general_specialist": "general_specialist",
            },
        )
        for node in [
            "laptop_specialist", "mobile_specialist", "tv_specialist",
            "refrigerator_specialist", "smart_watch_specialist",
            "washing_machine_specialist", "general_specialist",
        ]:
            graph.add_edge(node, END)

        return graph.compile()

    def analyze_product(self, product_name: str, category: str) -> dict:
        filters = {"category": category} if category else None
        docs, _ = self._retriever.retrieve(product_name, filters=filters)

        if not docs:
            return {
                "product_name": product_name,
                "category": category,
                "value_score": 0.0,
                "pros": [],
                "cons": ["Product not found in database"],
                "who_should_buy": "N/A",
                "who_should_avoid": "N/A",
                "better_alternatives": [],
                "verdict": "Product not found",
                "specs_summary": "No data available",
            }

        analysis_prompt = _ANALYSIS_PROMPTS.get(category, _ANALYSIS_PROMPTS["all"])
        context = _format_docs(docs)

        messages = [
            SystemMessage(content=analysis_prompt),
            HumanMessage(content=f"Target product: {product_name}\n\nAvailable product data:\n{context}"),
        ]
        raw = self._llm.invoke(messages).content
        parsed = _parse_response(raw)

        parsed.setdefault("value_score", 0.0)
        parsed.setdefault("pros", [])
        parsed.setdefault("cons", [])
        parsed.setdefault("who_should_buy", "")
        parsed.setdefault("who_should_avoid", "")
        parsed.setdefault("better_alternatives", [])
        parsed.setdefault("verdict", "")
        parsed.setdefault("specs_summary", "")
        parsed["product_name"] = product_name
        parsed["category"] = category

        return parsed

    def run(self, query: str, session_id: str, category: Optional[str] = None, filters: Optional[dict] = None) -> dict:
        history = self.session_store.get_last_n_turns(session_id, n=config.HISTORY_WINDOW)

        # First message in a category-scoped session → ask onboarding question
        if len(history) == 0 and category and category in _ONBOARDING_QUESTIONS:
            onboarding_q = _ONBOARDING_QUESTIONS[category]
            response = {
                "answer": onboarding_q,
                "products": [],
                "follow_ups": [],
                "intent": "onboarding",
                "rag_trace": {},
            }
            self.session_store.save_message(session_id, "user", query)
            self.session_store.save_message(session_id, "assistant", json.dumps(response))
            return response

        history_messages: list = []
        for msg in history:
            if msg["role"] == "user":
                history_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                history_messages.append(AIMessage(content=msg["content"]))

        initial_state: AgentState = {
            "query": query,
            "history_messages": history_messages,
            "category": "all",
            "forced_category": category,
            "filters": filters,
            "response": {},
            "last_docs": [],
            "last_meta": None,
        }

        result_box: list = []
        exc_box: list = []

        def _target():
            try:
                result = self._graph.invoke(initial_state)
                result_box.append(result)
            except Exception as e:
                exc_box.append(e)

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout=_AGENT_TIMEOUT)

        if result_box:
            final_state = result_box[0]
            self._last_state = final_state
            response = final_state.get("response", {})
        elif exc_box:
            response = {
                "answer": f"Agent error: {exc_box[0]}",
                "products": [], "follow_ups": [], "intent": "general", "rag_trace": {},
            }
        else:
            response = {
                "answer": f"Request timed out (>{_AGENT_TIMEOUT}s). Try a simpler query.",
                "products": [], "follow_ups": [], "intent": "general", "rag_trace": {},
            }

        self.session_store.save_message(session_id, "user", query)
        self.session_store.save_message(session_id, "assistant", json.dumps(response))
        self.session_store.summarize_old_messages(session_id)

        return response

    def get_last_contexts(self) -> list[str]:
        docs = self._last_state.get("last_docs", [])
        return [doc.page_content for doc in docs]
