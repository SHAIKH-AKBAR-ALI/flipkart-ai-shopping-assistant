from agents.common import run_retrieval_agent
from agents.state import AgentState

_SYSTEM_PROMPT = (
    "You are a Sales Advisor for a shopping assistant. Focus strictly on "
    "commercial terms: price, EMI options, bank offers, exchange offers, and "
    "availability. Use only the products given in the catalog context — never "
    "invent products or prices. Keep the answer concise (3-5 sentences)."
)


def make_sales_agent_node(retriever, llm):
    def sales_agent_node(state: AgentState) -> AgentState:
        return run_retrieval_agent(state, retriever, llm, _SYSTEM_PROMPT)

    return sales_agent_node
