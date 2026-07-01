import os

from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from agents.booking_agent import make_booking_agent_node
from agents.sales_agent import make_sales_agent_node
from agents.supervisor import make_supervisor_node, route_after_supervisor
from agents.state import AgentState
from agents.technical_agent import make_technical_agent_node
from rag.retriever import HybridRetriever


def build_graph(retriever: HybridRetriever = None, llm=None):
    """Builds and compiles the Supervisor + multi-agent LangGraph once.

    START -> supervisor -> (conditional: sales|technical|booking|end)
           -> sub-agent -> supervisor -> (end, since _agent_responded is set)
    """
    if llm is None:
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.environ["GROQ_API_KEY"],
            temperature=0.1,
        )
    if retriever is None:
        retriever = HybridRetriever()

    graph = StateGraph(AgentState)
    graph.add_node("supervisor", make_supervisor_node(llm))
    graph.add_node("sales", make_sales_agent_node(retriever, llm))
    graph.add_node("technical", make_technical_agent_node(retriever, llm))
    graph.add_node("booking", make_booking_agent_node(llm))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"sales": "sales", "technical": "technical", "booking": "booking", "end": END},
    )
    graph.add_edge("sales", "supervisor")
    graph.add_edge("technical", "supervisor")
    graph.add_edge("booking", "supervisor")

    return graph.compile()
