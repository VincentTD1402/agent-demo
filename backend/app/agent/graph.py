"""Lắp đồ thị: START -> agent -> (approve | tools | remember) ; tools -> agent."""
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from app.agent.nodes import approve, make_agent_node, remember
from app.agent.routing import route_after_agent


def build_graph(
    llm: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver,
    store: BaseStore,
):
    user_scoped = {t.name for t in tools if "user_id" in (t.args or {})}

    g = StateGraph(MessagesState)
    g.add_node("agent", make_agent_node(llm.bind_tools(tools), user_scoped))
    g.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    # approve trả Command(goto=...) nên khai báo đích để vẽ được đồ thị
    g.add_node("approve", approve, destinations=("tools", "agent"))
    g.add_node("remember", remember)

    g.add_edge(START, "agent")
    g.add_conditional_edges(
        "agent", route_after_agent, {"approve": "approve", "tools": "tools", "remember": "remember"}
    )
    g.add_edge("tools", "agent")  # vòng ReAct
    g.add_edge("remember", END)
    return g.compile(checkpointer=checkpointer, store=store)
