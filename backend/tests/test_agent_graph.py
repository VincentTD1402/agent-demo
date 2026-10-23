"""Kiểm thử đồ thị ShopBot với model giả (không cần server AI) và checkpointer/store trong bộ nhớ."""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.agent.graph import build_graph
from app.agent.routing import route_after_agent

REFUNDS: list[tuple] = []


@tool
def lookup_order(order_id: str, user_id: str) -> dict:
    """lookup"""
    return {"found": True, "id": order_id, "user": user_id}


@tool
def issue_refund(order_id: str, user_id: str, amount_vnd: int, reason: str) -> dict:
    """refund"""
    REFUNDS.append((order_id, user_id, amount_vnd))
    return {"ok": True}


class FakeLLM(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args, id_):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id_}])


def make(script):
    return build_graph(
        FakeLLM(messages=iter(script)), [lookup_order, issue_refund], InMemorySaver(), InMemoryStore()
    )


def cfg(thread="t1", user="u1"):
    return {"configurable": {"thread_id": thread, "user_id": user}, "recursion_limit": 12}


def test_route_after_agent():
    assert route_after_agent({"messages": [AIMessage("xin chào")]}) == "remember"
    assert route_after_agent({"messages": [call("lookup_order", {}, "1")]}) == "tools"
    assert route_after_agent({"messages": [call("issue_refund", {}, "1")]}) == "approve"


async def test_refund_pauses_then_executes_on_approval():
    REFUNDS.clear()
    g = make([
        call("lookup_order", {"order_id": "A100", "user_id": "hacker"}, "1"),
        call("issue_refund", {"order_id": "A100", "user_id": "hacker", "amount_vnd": 890000, "reason": "lỗi"}, "2"),
        AIMessage("Đã gửi yêu cầu hoàn tiền, chờ nhân viên duyệt."),
    ])
    r = await g.ainvoke({"messages": [("user", "hoàn tiền A100")]}, cfg())
    assert "__interrupt__" in r and REFUNDS == []  # chưa có tác dụng phụ trước khi duyệt
    assert r["__interrupt__"][0].value["actions"][0]["tool"] == "issue_refund"

    r = await g.ainvoke(Command(resume={"approved": True}), cfg())
    assert REFUNDS == [("A100", "u1", 890000)]  # user_id bị ép về phiên, không tin LLM
    assert r["messages"][-1].content == "Đã gửi yêu cầu hoàn tiền, chờ nhân viên duyệt."


async def test_rejection_skips_refund():
    REFUNDS.clear()
    g = make([
        call("issue_refund", {"order_id": "A100", "user_id": "u1", "amount_vnd": 1, "reason": "x"}, "1"),
        AIMessage("Yêu cầu bị từ chối."),
    ])
    await g.ainvoke({"messages": [("user", "hoàn tiền")]}, cfg())
    r = await g.ainvoke(Command(resume={"approved": False, "note": "sai"}), cfg())
    assert REFUNDS == []
    assert r["messages"][-1].content == "Yêu cầu bị từ chối."


async def test_thread_metadata_records_owner():
    g = make([AIMessage("chào")])
    await g.ainvoke({"messages": [("user", "hi")]}, cfg(thread="own", user="alice"))
    snap = await g.aget_state({"configurable": {"thread_id": "own"}})
    assert snap.metadata["user_id"] == "alice"


def test_system_prompt_says_refund_is_only_a_request_to_staff():
    from app.agent.prompts import SYSTEM_PROMPT

    assert "pending_staff" in SYSTEM_PROMPT and "CHƯA được hoàn" in SYSTEM_PROMPT
    assert "tuyệt đối không nói" in SYSTEM_PROMPT and "pending_refund_vnd" in SYSTEM_PROMPT
