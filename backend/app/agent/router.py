"""API chat: POST /chat (một lần), POST /chat/stream (SSE), DELETE /chat/{thread_id} (xoá hội thoại)."""

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.reranker_client import RerankError
from app.agent.runner import ChatResult, run_chat, stream_chat
from app.api_key_auth import require_api_key
from app.embedding_client import EmbeddingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])

# Lỗi dịch vụ phụ trợ (embedding/rerank/LLM/DB) -> báo 502 thay vì 500 để client biết là tạm thời
_UPSTREAM_ERRORS = (EmbeddingError, RerankError, ConnectionError, TimeoutError, OSError)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Để trống = mở hội thoại mới; thread_id là khoá truy cập hội thoại nên server tự sinh UUID khó đoán
    thread_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


class SourceOut(BaseModel):
    source: str
    score: float


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    route: str = Field(description="chat | rag | out_of_scope")
    sources: list[SourceOut] = []


async def _runtime(request: Request):
    runtime = request.app.state.agent
    try:
        await runtime.ensure_ready()
    except Exception:
        logger.exception("Agent chưa sẵn sàng")
        raise HTTPException(status_code=503, detail="Dịch vụ chat chưa sẵn sàng, thử lại sau") from None
    return runtime


def _response(result: ChatResult) -> ChatResponse:
    return ChatResponse(**{**result.__dict__, "sources": [SourceOut(**s) for s in result.sources]})


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    runtime = await _runtime(request)
    thread_id = body.thread_id or uuid.uuid4().hex
    try:
        return _response(await run_chat(runtime.graph, thread_id, body.message))
    except _UPSTREAM_ERRORS:
        logger.exception("Lỗi dịch vụ phụ trợ khi chat")
        raise HTTPException(status_code=502, detail="Dịch vụ AI tạm thời gặp lỗi, thử lại sau") from None


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """SSE: `{"type":"token","content":...}` ... rồi `{"type":"done",...}`; lỗi giữa chừng gửi `{"type":"error"}`."""
    runtime = await _runtime(request)
    thread_id = body.thread_id or uuid.uuid4().hex

    async def events() -> AsyncIterator[str]:
        try:
            async for item in stream_chat(runtime.graph, thread_id, body.message):
                if isinstance(item, str):
                    yield _sse({"type": "token", "content": item})
                else:
                    yield _sse({"type": "done", **_response(item).model_dump()})
        except Exception:
            logger.exception("Lỗi khi stream câu trả lời")
            yield _sse({"type": "error", "detail": "Dịch vụ AI tạm thời gặp lỗi, thử lại sau"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@router.delete("/{thread_id}")
async def delete_chat(thread_id: str, request: Request) -> dict[str, str]:
    runtime = await _runtime(request)
    await runtime.delete_thread(thread_id)
    return {"deleted": thread_id}
