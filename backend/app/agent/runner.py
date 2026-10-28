"""Chạy đồ thị cho một lượt chat: trả kết quả một lần hoặc phát từng token."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from app.agent.llm import message_text, raw_text
from app.agent.state import AgentState

# Chỉ các node trả lời gửi khách mới được phát token (analyze/summarize là bước nội bộ)
_REPLY_NODES = frozenset({"chat", "generate", "decline", "shop_agent"})
# Vòng gọi tool tối đa ~9 lượt (mỗi lượt = node shop_agent + node tools); vượt thì dừng thay vì lặp mãi
_RECURSION_LIMIT = 20
_TOO_COMPLEX = "Xin lỗi, yêu cầu này hơi phức tạp nên mình chưa xử lý xong. Bạn thử chia nhỏ yêu cầu giúp mình nhé."


@dataclass(frozen=True)
class ChatResult:
    thread_id: str
    reply: str
    route: str
    sources: list[dict] = field(default_factory=list)


def _config(thread_id: str, session_id: str) -> dict:
    # session_id do server đặt: tool giỏ hàng/đơn hàng lấy từ đây, model không điền được (xem shop_tools.py)
    return {"configurable": {"thread_id": thread_id, "session_id": session_id}, "recursion_limit": _RECURSION_LIMIT}


def _result(thread_id: str, state: AgentState) -> ChatResult:
    # Câu trả lời cuối là tin nhắn AI không kèm tool_call (tin nhắn có tool_call chỉ là bước trung gian)
    reply = next(
        (message_text(m.content) for m in reversed(state["messages"]) if isinstance(m, AIMessage) and not m.tool_calls), ""
    )
    # Nguồn tham khảo: mỗi tài liệu một lần, giữ điểm cao nhất
    best: dict[str, float] = {}
    for chunk in state.get("documents", []):
        best[chunk["source"]] = max(best.get(chunk["source"], 0.0), chunk["score"])
    sources = [{"source": s, "score": round(v, 3)} for s, v in sorted(best.items(), key=lambda kv: -kv[1])]
    return ChatResult(thread_id, reply, state.get("route", "rag"), sources)


async def run_chat(graph: CompiledStateGraph, thread_id: str, session_id: str, message: str) -> ChatResult:
    try:
        state = await graph.ainvoke({"messages": [HumanMessage(message)]}, _config(thread_id, session_id))
    except GraphRecursionError:
        return ChatResult(thread_id, _TOO_COMPLEX, "shop")
    return _result(thread_id, state)


async def stream_chat(
    graph: CompiledStateGraph, thread_id: str, session_id: str, message: str
) -> AsyncIterator[str | ChatResult]:
    """Phát các đoạn văn bản của câu trả lời, cuối cùng phát ChatResult (route + nguồn)."""
    streamed_ids: set[str] = set()
    config = _config(thread_id, session_id)
    try:
        async for chunk, metadata in graph.astream({"messages": [HumanMessage(message)]}, config, stream_mode="messages"):
            if metadata.get("langgraph_node") not in _REPLY_NODES or not isinstance(chunk, AIMessage):
                continue
            text = raw_text(chunk.content)  # không strip: khoảng trắng đầu token là một phần câu trả lời
            # Model có stream thì nhận từng mảnh; model không stream thì nhận nguyên tin nhắn, tránh phát trùng theo id
            if text and (chunk.type == "AIMessageChunk" or chunk.id not in streamed_ids):
                streamed_ids.add(chunk.id)
                yield text
    except GraphRecursionError:
        yield _TOO_COMPLEX
        yield ChatResult(thread_id, _TOO_COMPLEX, "shop")
        return
    state = (await graph.aget_state(config)).values
    yield _result(thread_id, state)
