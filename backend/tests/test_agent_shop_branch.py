"""Nhánh shop của agent (vòng gọi tool) bằng model và tool giả: không cần mạng/DB/MCP server."""

import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_agent_graph
from app.agent.nodes import AgentNodes, SummaryPolicy, orphan_tool_call_ids, window
from app.agent.runner import run_chat
from app.agent.shop_tools import bind_session

SESSION = "session-aaaaaaaaaaaa"


class FakeSearcher:
    def __init__(self, chunks=()):
        self.chunks, self.questions = list(chunks), []

    def search(self, question):
        self.questions.append(question)
        return self.chunks


class ScriptedShopLLM:
    """Model giả đã bind tool: mỗi lần gọi trả về tin nhắn kế tiếp trong kịch bản, với tool_call id riêng."""

    def __init__(self, script):
        self._script, self.calls = list(script), 0

    async def ainvoke(self, messages):
        message = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return AIMessage(content=message.content, tool_calls=[dict(c, id=f"{c['id']}-{self.calls}") for c in message.tool_calls])


def tool_call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call"}])


def analysis(route, query="q"):
    return json.dumps({"route": route, "query": query})


def make_tool(seen):
    async def add_to_cart(session_id: str, slug: str, quantity: int = 1) -> str:
        seen.append({"session_id": session_id, "slug": slug, "quantity": quantity})
        return json.dumps({"ok": True, "cart": {"total_vnd": 290000}})

    schema = {
        "type": "object",
        "properties": {"session_id": {"type": "string"}, "slug": {"type": "string"}, "quantity": {"type": "integer"}},
        "required": ["session_id", "slug"],
    }
    return bind_session(StructuredTool(name="add_to_cart", description="Add to cart", coroutine=add_to_cart, args_schema=schema))


def make_graph(fast_replies, answer_replies=("ok",), shop_llm=None, tools=None, chunks=()):
    searcher = FakeSearcher(chunks)
    nodes = AgentNodes(
        FakeListChatModel(responses=list(fast_replies)), FakeListChatModel(responses=list(answer_replies)),
        searcher, SummaryPolicy(40, 6), shop_llm=shop_llm,
    )
    return build_agent_graph(nodes, InMemorySaver(), tools), searcher


def thread(tid):
    return {"configurable": {"thread_id": tid}}


def test_session_id_is_hidden_from_model_schema():
    tool = make_tool([])
    assert "session_id" not in tool.args_schema["properties"] and "session_id" not in tool.args_schema["required"]


async def test_shop_route_runs_tool_with_server_session_and_ignores_model_supplied_one():
    seen = []
    llm = ScriptedShopLLM([
        tool_call("add_to_cart", slug="anker-sac-20w", quantity=1, session_id="attacker-session-9999"),
        AIMessage(content="Đã thêm củ sạc vào giỏ."),
    ])
    graph, searcher = make_graph([analysis("shop")], shop_llm=llm, tools=[make_tool(seen)])
    result = await run_chat(graph, "t10", SESSION, "thêm củ sạc anker vào giỏ")
    assert (result.route, result.reply) == ("shop", "Đã thêm củ sạc vào giỏ.")
    assert seen == [{"session_id": SESSION, "slug": "anker-sac-20w", "quantity": 1}]  # không phải attacker-session-9999
    assert searcher.questions == []
    state = (await graph.aget_state(thread("t10"))).values
    assert [m.type for m in state["messages"]] == ["human", "ai", "tool", "ai"]


async def test_shop_route_falls_back_to_rag_when_tools_unavailable():
    chunk = {"source": "policies/x.md", "content": "Nội dung chính sách.", "score": 0.9}
    graph, searcher = make_graph([analysis("shop", "giá iPhone 16?")], ["Theo tài liệu..."], tools=None, chunks=[chunk])
    result = await run_chat(graph, "t11", SESSION, "giá iPhone 16?")
    assert result.reply == "Theo tài liệu..." and searcher.questions == ["giá iPhone 16?"]


async def test_tool_loop_limit_stops_and_next_turn_recovers_from_dangling_tool_call():
    seen = []
    loop = ScriptedShopLLM([tool_call("add_to_cart", slug="anker-sac-20w")])  # model gọi tool mãi không dừng
    graph, _ = make_graph([analysis("shop"), analysis("chat")], ["Chào bạn!"], shop_llm=loop, tools=[make_tool(seen)])
    first = await run_chat(graph, "t12", SESSION, "thêm củ sạc")
    assert "phức tạp" in first.reply and len(seen) >= 2
    second = await run_chat(graph, "t12", SESSION, "cảm ơn")
    assert second.reply == "Chào bạn!"
    state = (await graph.aget_state(thread("t12"))).values
    assert orphan_tool_call_ids(state["messages"]) == []


def test_orphan_tool_call_ids_detects_unanswered_calls_only():
    call = [{"name": "x", "args": {}, "id": "c1"}]
    answered = [HumanMessage("a", id="h1"), AIMessage("", id="a1", tool_calls=call),
                ToolMessage("r", tool_call_id="c1", id="t1"), AIMessage("xong", id="a2")]
    assert orphan_tool_call_ids(answered) == []
    assert orphan_tool_call_ids(answered[:2]) == ["a1"]


def test_window_never_starts_in_the_middle_of_a_tool_exchange():
    call = [{"name": "x", "args": {}, "id": "c1"}]
    msgs = [HumanMessage("1", id="h1"), AIMessage("", id="a1", tool_calls=call), ToolMessage("r", tool_call_id="c1", id="t1"),
            AIMessage("xong", id="a2"), HumanMessage("2", id="h2"), AIMessage("ok", id="a3")]
    assert [m.id for m in window(msgs, 3)] == ["h2", "a3"]  # cắt giữa cặp tool thì tiến tới tin nhắn khách kế tiếp
    assert [m.id for m in window(msgs, 6)][0] == "h1"
    assert [m.id for m in window(msgs[:4], 2)][0] == "h1"  # cửa sổ không có tin nhắn khách: lùi về tin nhắn khách gần nhất
