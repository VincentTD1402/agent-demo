"""Đồ thị agent RAG (LangGraph).

START -> analyze --chat--------------> chat ----------+
                 --out_of_scope-------> decline -------+--> summarize (nếu hội thoại dài) -> END
                 --rag--> retrieve --có tài liệu--> generate --+
                                   --không có------> decline --+
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import AgentNodes
from app.agent.state import AgentState


def build_agent_graph(nodes: AgentNodes, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("analyze", nodes.analyze)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("generate", nodes.generate)
    builder.add_node("chat", nodes.chat)
    builder.add_node("decline", nodes.decline)
    builder.add_node("summarize", nodes.summarize)

    builder.add_edge(START, "analyze")
    builder.add_conditional_edges(
        "analyze",
        lambda state: state["route"],
        {"chat": "chat", "rag": "retrieve", "out_of_scope": "decline"},
    )
    builder.add_conditional_edges(
        "retrieve", lambda state: "generate" if state["documents"] else "decline", {"generate": "generate", "decline": "decline"}
    )
    for reply_node in ("chat", "generate", "decline"):
        builder.add_conditional_edges(
            reply_node,
            lambda state: "summarize" if nodes.needs_summary(state) else "end",
            {"summarize": "summarize", "end": END},
        )
    builder.add_edge("summarize", END)
    return builder.compile(checkpointer=checkpointer)
