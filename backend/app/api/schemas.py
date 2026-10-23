from typing import Literal

from pydantic import BaseModel, Field

# user_id/thread_id chỉ cho phép ký tự an toàn vì được dùng làm khoá namespace/checkpoint
_ID = r"^[A-Za-z0-9_.:@-]{1,128}$"


class ChatRequest(BaseModel):
    user_id: str = Field(pattern=_ID)
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, pattern=_ID, description="Bỏ trống để mở hội thoại mới")


class ResumeRequest(BaseModel):
    user_id: str = Field(pattern=_ID)
    approved: bool
    note: str | None = Field(default=None, max_length=500)


class PendingAction(BaseModel):
    tool: str
    args: dict


class ChatResponse(BaseModel):
    thread_id: str
    status: Literal["completed", "awaiting_approval"]
    reply: str | None = None
    pending_actions: list[PendingAction] = []
