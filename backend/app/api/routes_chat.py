"""Endpoint hội thoại: gửi tin, và resume sau khi người duyệt quyết định."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.api.deps import get_graph, require_api_key
from app.api.schemas import ChatRequest, ChatResponse, PendingAction, ResumeRequest
from app.settings.api import ApiSettings, get_api_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


def _final_text(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            if isinstance(m.content, str):
                return m.content
            return "".join(p.get("text", "") for p in m.content if isinstance(p, dict))
    return ""


def _to_response(thread_id: str, result: dict) -> ChatResponse:
    interrupts = result.get("__interrupt__")
    if interrupts:
        actions = interrupts[0].value.get("actions", [])
        return ChatResponse(
            thread_id=thread_id,
            status="awaiting_approval",
            pending_actions=[PendingAction(**a) for a in actions],
        )
    return ChatResponse(thread_id=thread_id, status="completed", reply=_final_text(result["messages"]))


async def _run(graph, payload, thread_id: str, user_id: str, settings: ApiSettings) -> ChatResponse:
    config = {
        "configurable": {"thread_id": thread_id, "user_id": user_id},
        # Chặn vòng lặp vô tận (lỗi công cụ lặp lại tốn tiền)
        "recursion_limit": settings.agent_max_steps,
    }
    try:
        result = await graph.ainvoke(payload, config)
    except Exception:
        log.exception("agent run failed thread=%s", thread_id)
        raise HTTPException(502, "Agent gặp lỗi khi xử lý, vui lòng thử lại.")
    return _to_response(thread_id, result)


async def _assert_owner(graph, thread_id: str, user_id: str) -> None:
    """Thread thuộc về user đã tạo ra nó; user khác không được đọc/resume."""
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    owner = (snap.metadata or {}).get("user_id")
    if not snap.created_at or owner != user_id:
        raise HTTPException(404, "thread not found")


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    graph=Depends(get_graph),
    settings: ApiSettings = Depends(get_api_settings),
):
    thread_id = req.thread_id or uuid.uuid4().hex
    if req.thread_id:
        await _assert_owner(graph, thread_id, req.user_id)
    return await _run(
        graph, {"messages": [("user", req.message)]}, thread_id, req.user_id, settings
    )


@router.post("/{thread_id}/resume", response_model=ChatResponse)
async def resume(
    thread_id: str,
    req: ResumeRequest,
    graph=Depends(get_graph),
    settings: ApiSettings = Depends(get_api_settings),
):
    await _assert_owner(graph, thread_id, req.user_id)
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if not snap.interrupts:
        raise HTTPException(409, "Hội thoại không có yêu cầu nào đang chờ duyệt.")
    decision = {"approved": req.approved, "note": req.note}
    return await _run(graph, Command(resume=decision), thread_id, req.user_id, settings)
