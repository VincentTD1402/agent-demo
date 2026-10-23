"""Điều hướng đồ thị bằng code (deterministic), không để LLM tự chọn node."""
from langchain_core.messages import AIMessage, AnyMessage

# Công cụ có hậu quả thật: luôn dừng chờ người duyệt
SENSITIVE_TOOLS = frozenset({"issue_refund"})


def route_after_agent(state: dict) -> str:
    """tool_call nhạy cảm -> approve; tool_call thường -> tools; hết tool_call -> remember."""
    last: AnyMessage = state["messages"][-1]
    calls = last.tool_calls if isinstance(last, AIMessage) else []
    if not calls:
        return "remember"
    if any(c["name"] in SENSITIVE_TOOLS for c in calls):
        return "approve"
    return "tools"
