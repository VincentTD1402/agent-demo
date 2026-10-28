"""Trạng thái của đồ thị agent; được checkpointer lưu theo từng thread (cuộc hội thoại)."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Route = Literal["chat", "rag", "out_of_scope"]
DeclineReason = Literal["out_of_scope", "no_info"]


class RetrievedChunk(TypedDict):
    source: str  # tên file / đường dẫn tương đối của tài liệu
    content: str
    score: float  # điểm rerank 0..1


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str  # tóm tắt phần hội thoại cũ đã bị cắt khỏi messages
    route: Route
    question: str  # câu hỏi độc lập (đã giải nghĩa đại từ) dùng để tìm tài liệu
    documents: list[RetrievedChunk]  # reset mỗi lượt để không dùng nhầm tài liệu của lượt trước
    decline_reason: DeclineReason
