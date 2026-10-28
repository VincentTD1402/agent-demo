"""Dựng các model chat (API tương thích OpenAI) và tiện ích đọc kết quả."""

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.settings import Settings

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _chat_model(settings: Settings, temperature: float, max_tokens: int) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_api_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=settings.llm_timeout,
        max_retries=1,
        # Qwen3: tắt chế độ suy nghĩ để trả lời nhanh và không lẫn thẻ <think> vào câu trả lời
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def build_fast_llm(settings: Settings) -> BaseChatModel:
    """Cho các bước nội bộ (phân loại, viết lại câu hỏi, tóm tắt): xác định, ngắn."""
    return _chat_model(settings, temperature=0.0, max_tokens=300)


def build_answer_llm(settings: Settings) -> BaseChatModel:
    """Cho câu trả lời gửi khách."""
    return _chat_model(settings, settings.rag_answer_temperature, settings.llm_max_tokens)


def raw_text(content: str | list) -> str:
    """Nội dung tin nhắn về dạng chuỗi, giữ nguyên khoảng trắng (dùng cho từng mảnh khi stream)."""
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return content


def message_text(content: str | list) -> str:
    """Nội dung AIMessage hoàn chỉnh: bỏ khối <think> nếu model vẫn sinh ra, cắt khoảng trắng hai đầu."""
    return _THINK_BLOCK.sub("", raw_text(content)).strip()


def parse_json_object(text: str) -> dict | None:
    """Lấy object JSON đầu tiên trong `text` (model đôi khi bọc trong ```json ... ```); None nếu không đọc được."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
