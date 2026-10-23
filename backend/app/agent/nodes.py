"""Các node của đồ thị ShopBot: agent, approve, remember."""
import logging
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState
from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.routing import SENSITIVE_TOOLS

log = logging.getLogger(__name__)
MEMORY_LIMIT = 3


def _user_id(config: RunnableConfig) -> str:
    return config["configurable"]["user_id"]


def _last_human_text(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


async def _recall(store: BaseStore, user_id: str, query: str) -> str:
    """Tra bộ nhớ dài hạn (ngữ nghĩa). Lỗi bộ nhớ không được làm hỏng cuộc trò chuyện."""
    try:
        items = await store.asearch((user_id, "profile"), query=query or None, limit=MEMORY_LIMIT)
    except Exception:
        log.exception("memory recall failed")
        return "(không có)"
    lines = [f"- {i.value['text']}" for i in items if "text" in i.value]
    return "\n".join(lines) or "(chưa có)"


def make_agent_node(llm_with_tools, user_scoped_tools: set[str]):
    async def agent(state: MessagesState, config: RunnableConfig, *, store: BaseStore):
        user_id = _user_id(config)
        memory = await _recall(store, user_id, _last_human_text(state["messages"]))
        system = SystemMessage(SYSTEM_PROMPT.format(user_id=user_id, memory=memory))
        reply: AIMessage = await llm_with_tools.ainvoke([system, *state["messages"]])
        # LLM không được quyết định danh tính: ép user_id từ phiên đăng nhập
        for call in reply.tool_calls:
            if call["name"] in user_scoped_tools:
                call["args"]["user_id"] = user_id
        return {"messages": [reply]}

    return agent


def approve(state: MessagesState):
    """Cổng người duyệt. Chỉ làm việc nhẹ rồi interrupt(); tác dụng phụ nằm ở node tools."""
    ai: AIMessage = state["messages"][-1]
    decision = interrupt(
        {
            "type": "approval_required",
            "actions": [
                {"tool": c["name"], "args": c["args"]}
                for c in ai.tool_calls
                if c["name"] in SENSITIVE_TOOLS
            ],
        }
    )
    if decision.get("approved"):
        return Command(goto="tools")
    note = decision.get("note") or "không nêu lý do"
    rejected = [
        ToolMessage(
            content=f"Người duyệt đã TỪ CHỐI hành động này ({note}). Không thực hiện.",
            tool_call_id=c["id"],
            name=c["name"],
        )
        for c in ai.tool_calls
    ]
    return Command(goto="agent", update={"messages": rejected})


async def remember(state: MessagesState, config: RunnableConfig, *, store: BaseStore):
    """Ghi yêu cầu gần nhất vào bộ nhớ dài hạn của khách."""
    text = _last_human_text(state["messages"])
    if text:
        try:
            await store.aput(
                (_user_id(config), "profile"),
                "last_request",
                {"text": f"Yêu cầu gần nhất: {text}", "ts": datetime.now(timezone.utc).isoformat()},
            )
        except Exception:
            log.exception("memory write failed")
    return {}
