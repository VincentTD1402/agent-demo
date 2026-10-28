"""Đồ thị agent (LangGraph): RAG + nhánh mua sắm dùng tool qua MCP.

START -> analyze --chat---------------> chat ----------------------------+
                 --out_of_scope-------> decline -------------------------+
                 --rag--> retrieve --có tài liệu--> generate ------------+--> summarize (nếu hội thoại dài) -> END
                                   --không có------> decline -----------+
                 --shop--> shop_agent <--> tools   (lặp tới khi model trả lời) --+

Nhánh shop tắt (không có tool) thì route "shop" đi theo nhánh RAG.
"""

from collections.abc import Sequence

from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.agent.nodes import AgentNodes
from app.agent.state import AgentState


def build_agent_graph(
    nodes: AgentNodes, checkpointer: BaseCheckpointSaver, tools: Sequence[BaseTool] | None = None
) -> CompiledStateGraph:
    shop_enabled = bool(tools)
    builder = StateGraph(AgentState)
    builder.add_node("analyze", nodes.analyze)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("generate", nodes.generate)
    builder.add_node("chat", nodes.chat)
    builder.add_node("decline", nodes.decline)
    builder.add_node("summarize", nodes.summarize)

    builder.add_edge(START, "analyze")
    routes = {"chat": "chat", "rag": "retrieve", "shop": "retrieve", "out_of_scope": "decline"}
    if shop_enabled:
        builder.add_node("shop_agent", nodes.shop_agent)
        # handle_tool_errors: lỗi tool (vd MCP server tạm thời không phản hồi) thành ToolMessage để model báo lại cho khách
        builder.add_node("tools", ToolNode(list(tools), handle_tool_errors=True))
        routes["shop"] = "shop_agent"
        builder.add_conditional_edges(
            "shop_agent",
            lambda state: "tools" if nodes.wants_tools(state) else ("summarize" if nodes.needs_summary(state) else "end"),
            {"tools": "tools", "summarize": "summarize", "end": END},
        )
        builder.add_edge("tools", "shop_agent")
    builder.add_conditional_edges("analyze", lambda state: state["route"], routes)
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
