"""Chạy đồ thị cho một lượt chat: trả kết quả một lần hoặc phát từng token."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.llm import message_text, raw_text
from app.agent.state import AgentState

# Chỉ các node trả lời gửi khách mới được phát token (analyze/summarize là bước nội bộ)
_REPLY_NODES = frozenset({"chat", "generate", "decline"})


@dataclass(frozen=True)
class ChatResult:
    thread_id: str
    reply: str
    route: str
    sources: list[dict] = field(default_factory=list)


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _result(thread_id: str, state: AgentState) -> ChatResult:
    reply = next((message_text(m.content) for m in reversed(state["messages"]) if isinstance(m, AIMessage)), "")
    # Nguồn tham khảo: mỗi tài liệu một lần, giữ điểm cao nhất
    best: dict[str, float] = {}
    for chunk in state.get("documents", []):
        best[chunk["source"]] = max(best.get(chunk["source"], 0.0), chunk["score"])
    sources = [{"source": s, "score": round(v, 3)} for s, v in sorted(best.items(), key=lambda kv: -kv[1])]
    return ChatResult(thread_id, reply, state.get("route", "rag"), sources)


async def run_chat(graph: CompiledStateGraph, thread_id: str, message: str) -> ChatResult:
    state = await graph.ainvoke({"messages": [HumanMessage(message)]}, _config(thread_id))
    return _result(thread_id, state)


async def stream_chat(graph: CompiledStateGraph, thread_id: str, message: str) -> AsyncIterator[str | ChatResult]:
    """Phát các đoạn văn bản của câu trả lời, cuối cùng phát ChatResult (route + nguồn)."""
    streamed_ids: set[str] = set()
    async for chunk, metadata in graph.astream(
        {"messages": [HumanMessage(message)]}, _config(thread_id), stream_mode="messages"
    ):
        if metadata.get("langgraph_node") not in _REPLY_NODES or not isinstance(chunk, AIMessage):
            continue
        text = raw_text(chunk.content)  # không strip: khoảng trắng đầu token là một phần câu trả lời
        # Model có stream thì nhận từng mảnh; model không stream thì nhận nguyên tin nhắn, tránh phát trùng theo id
        if text and (chunk.type == "AIMessageChunk" or chunk.id not in streamed_ids):
            streamed_ids.add(chunk.id)
            yield text
    state = (await graph.aget_state(_config(thread_id))).values
    yield _result(thread_id, state)
