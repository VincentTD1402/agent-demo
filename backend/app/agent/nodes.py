"""Các node của đồ thị agent. Mỗi node nhận state và trả về phần state cần cập nhật."""

import asyncio
import logging
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable

from app.agent import prompts
from app.agent.llm import message_text, parse_json_object
from app.agent.retrieval import ChunkSearcher
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_VALID_ROUTES = {"chat", "rag", "shop", "out_of_scope"}
_ANALYZE_WINDOW = 6  # số tin nhắn gần nhất đưa vào bước phân loại/viết lại câu hỏi
_ANSWER_WINDOW = 10  # số tin nhắn gần nhất đưa vào bước trả lời
_SHOP_WINDOW = 24  # vòng gọi tool sinh nhiều tin nhắn (AI tool_call + kết quả) nên cần cửa sổ rộng hơn


@dataclass(frozen=True)
class SummaryPolicy:
    summarize_after: int  # số tin nhắn trong state vượt ngưỡng này thì tóm tắt
    keep_messages: int  # giữ lại bấy nhiêu tin nhắn gần nhất sau khi tóm tắt


def _fill(template: str, **values: str) -> str:
    # Không dùng str.format: prompt chứa dấu ngoặc nhọn của ví dụ JSON
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def _last_user_text(messages: list[AnyMessage]) -> str:
    return next((message_text(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), "")


def window(messages: list[AnyMessage], size: int) -> list[AnyMessage]:
    """`size` tin nhắn gần nhất, nhưng luôn bắt đầu từ tin nhắn của khách.

    Cắt giữa chừng có thể bỏ AIMessage(tool_calls) mà giữ ToolMessage kết quả của nó: API chat từ chối chuỗi đó.
    """
    tail = messages[-size:]
    start = next((i for i, m in enumerate(tail) if isinstance(m, HumanMessage)), None)
    if start is not None:
        return tail[start:]
    last_human = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), 0)
    return messages[last_human:]


def orphan_tool_call_ids(messages: list[AnyMessage]) -> list[str]:
    """Id các tin nhắn AI có tool_call mà chưa có đủ kết quả (vòng gọi tool bị ngắt: lỗi, quá giới hạn bước, khách ngắt kết nối).

    Giữ lại sẽ làm mọi lượt sau của hội thoại bị API từ chối, nên phải gỡ cùng các kết quả tool dở dang của nó.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    orphans: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls and any(call["id"] not in answered for call in m.tool_calls):
            orphans.add(m.id)
            orphans.update(t.id for t in messages if isinstance(t, ToolMessage) and t.tool_call_id in {c["id"] for c in m.tool_calls})
    return [i for i in orphans if i]


class AgentNodes:
    def __init__(
        self, fast_llm: BaseChatModel, answer_llm: BaseChatModel, searcher: ChunkSearcher, policy: SummaryPolicy,
        shop_llm: Runnable | None = None,
    ):
        self._fast = fast_llm
        self._answer = answer_llm
        self._searcher = searcher
        self._policy = policy
        self._shop = shop_llm  # model đã bind tool; None = nhánh shop tắt

    async def analyze(self, state: AgentState) -> dict:
        """Phân loại ý định và viết lại câu hỏi thành câu độc lập; lỗi/định dạng sai thì mặc định đi nhánh RAG."""
        messages = state["messages"]
        repair = [RemoveMessage(id=i) for i in orphan_tool_call_ids(messages)]
        if repair:
            logger.warning("Gỡ %d tin nhắn tool dở dang từ lượt trước", len(repair))
            messages = [m for m in messages if m.id not in {r.id for r in repair}]
        last_user = _last_user_text(messages)
        system = _fill(prompts.ANALYZE_SYSTEM, summary=state.get("summary") or "none")
        route, question = "rag", last_user
        try:
            response = await self._fast.ainvoke(
                [SystemMessage(system), *window(messages, _ANALYZE_WINDOW)], response_format={"type": "json_object"}
            )
            parsed = parse_json_object(message_text(response.content)) or {}
            if parsed.get("route") in _VALID_ROUTES:
                route = parsed["route"]
            if isinstance(parsed.get("query"), str) and parsed["query"].strip():
                question = parsed["query"].strip()
        except Exception:
            logger.exception("Phân loại câu hỏi thất bại, dùng nhánh RAG mặc định")
        logger.info("route=%s question=%r", route, question)
        update: dict = {"route": route, "question": question, "documents": []}
        if repair:
            update["messages"] = repair
        return update

    async def retrieve(self, state: AgentState) -> dict:
        chunks = await asyncio.to_thread(self._searcher.search, state["question"])
        logger.info("retrieved %d chunks (scores=%s)", len(chunks), [round(c["score"], 2) for c in chunks])
        return {"documents": chunks}

    async def generate(self, state: AgentState) -> dict:
        context = "\n\n".join(f"[{i}] {chunk['content']}" for i, chunk in enumerate(state["documents"], 1))
        system = _fill(prompts.GENERATE_SYSTEM, summary=state.get("summary") or "none", context=context)
        return await self._reply(system, state, self._answer)

    async def chat(self, state: AgentState) -> dict:
        system = _fill(prompts.CHAT_SYSTEM, summary=state.get("summary") or "none")
        return await self._reply(system, state, self._answer)

    async def decline(self, state: AgentState) -> dict:
        reason = "out_of_scope" if state.get("route") == "out_of_scope" else "no_info"
        return await self._reply(_fill(prompts.DECLINE_SYSTEM, reason=reason), state, self._answer)

    async def shop_agent(self, state: AgentState) -> dict:
        """Một bước của vòng lặp tool: model quyết định gọi tool (graph chuyển sang node tools) hoặc trả lời khách."""
        system = _fill(prompts.SHOP_SYSTEM, summary=state.get("summary") or "none")
        response = await self._shop.ainvoke([SystemMessage(system), *window(state["messages"], _SHOP_WINDOW)])
        logger.info("shop_agent tool_calls=%s", [(c["name"], c["args"]) for c in response.tool_calls])
        return {"messages": [response]}

    @staticmethod
    def wants_tools(state: AgentState) -> bool:
        last = state["messages"][-1]
        return isinstance(last, AIMessage) and bool(last.tool_calls)

    async def summarize(self, state: AgentState) -> dict:
        messages = state["messages"]
        cut = self._cut_index(messages)
        old = messages[:cut]
        transcript = "\n".join(f"{m.type}: {message_text(m.content)}" for m in old if m.content and m.type != "tool")  # kết quả tool dài, không cần cho bản tóm tắt
        system = _fill(prompts.SUMMARIZE_SYSTEM, summary=state.get("summary") or "none")
        response = await self._fast.ainvoke([SystemMessage(system), HumanMessage(transcript)])
        return {"summary": message_text(response.content), "messages": [RemoveMessage(id=m.id) for m in old]}

    def needs_summary(self, state: AgentState) -> bool:
        return len(state["messages"]) > self._policy.summarize_after

    def _cut_index(self, messages: list[AnyMessage]) -> int:
        """Vị trí bắt đầu phần giữ lại; luôn là tin nhắn của khách để đoạn hội thoại còn lại mở đầu hợp lệ."""
        cut = max(len(messages) - self._policy.keep_messages, 0)
        while cut < len(messages) and not isinstance(messages[cut], HumanMessage):
            cut += 1
        return cut

    @staticmethod
    async def _reply(system: str, state: AgentState, llm: BaseChatModel) -> dict:
        response = await llm.ainvoke([SystemMessage(system), *window(state["messages"], _ANSWER_WINDOW)])
        return {"messages": [AIMessage(content=message_text(response.content), id=response.id)]}
