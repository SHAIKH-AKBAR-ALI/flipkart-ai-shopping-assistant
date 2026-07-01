from agents.common import run_retrieval_agent
from agents.state import AgentState

_SYSTEM_PROMPT = (
    "You are a Technical Advisor for a shopping assistant. Focus strictly on "
    "specifications, feature explanations, comparisons, and pros/cons. Do not "
    "discuss pricing or offers. Use only the products given in the catalog "
    "context — never invent specs. Keep the answer concise (3-5 sentences)."
)


def make_technical_agent_node(retriever, llm):
    def technical_agent_node(state: AgentState) -> AgentState:
        return run_retrieval_agent(state, retriever, llm, _SYSTEM_PROMPT)

    return technical_agent_node
