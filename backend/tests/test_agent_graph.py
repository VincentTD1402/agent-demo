"""Test đồ thị agent bằng LLM giả (kịch bản có sẵn), searcher giả và InMemorySaver: không cần mạng/DB."""

import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_agent_graph
from app.agent.llm import message_text, parse_json_object
from app.agent.nodes import AgentNodes, SummaryPolicy
from app.agent.runner import run_chat, stream_chat

SESSION = "session-aaaaaaaaaaaa"
POLICY_CHUNK = {"source": "policies/chinh-sach-hoan-tien.md", "content": "Hoàn tiền trong 7 ngày.", "score": 0.99}


class FakeSearcher:
    def __init__(self, chunks):
        self.chunks, self.questions = chunks, []

    def search(self, question):
        self.questions.append(question)
        return self.chunks


def analysis(route, query="q"):
    return json.dumps({"route": route, "query": query})


def make_graph(fast_replies, answer_replies, chunks=(), policy=SummaryPolicy(12, 6)):
    searcher = FakeSearcher(list(chunks))
    nodes = AgentNodes(FakeListChatModel(responses=fast_replies), FakeListChatModel(responses=answer_replies), searcher, policy)
    return build_agent_graph(nodes, InMemorySaver()), searcher


async def test_rag_route_retrieves_with_rewritten_question_and_returns_sources():
    graph, searcher = make_graph([analysis("rag", "Hoàn tiền trong bao nhiêu ngày?")], ["Trong 7 ngày."], [POLICY_CHUNK])
    result = await run_chat(graph, "t1", SESSION, "bao lâu thì được hoàn tiền")
    assert (result.route, result.reply) == ("rag", "Trong 7 ngày.")
    assert searcher.questions == ["Hoàn tiền trong bao nhiêu ngày?"]
    assert result.sources == [{"source": "policies/chinh-sach-hoan-tien.md", "score": 0.99}]


async def test_chat_route_skips_retrieval():
    graph, searcher = make_graph([analysis("chat")], ["Xin chào!"], [POLICY_CHUNK])
    result = await run_chat(graph, "t2", SESSION, "chào shop")
    assert (result.route, result.reply, result.sources) == ("chat", "Xin chào!", [])
    assert searcher.questions == []


async def test_out_of_scope_declines_without_retrieval():
    graph, searcher = make_graph([analysis("out_of_scope")], ["Mình chỉ hỗ trợ về ShopMobile."], [POLICY_CHUNK])
    result = await run_chat(graph, "t3", SESSION, "thời tiết hôm nay?")
    assert result.route == "out_of_scope" and "ShopMobile" in result.reply and searcher.questions == []


async def test_rag_without_relevant_documents_declines():
    graph, searcher = make_graph([analysis("rag")], ["Mình chưa tìm thấy thông tin này."], chunks=[])
    result = await run_chat(graph, "t4", SESSION, "iPhone 99 giá bao nhiêu")
    assert result.route == "rag" and result.sources == [] and "chưa tìm thấy" in result.reply
    assert len(searcher.questions) == 1


@pytest.mark.parametrize("bad_output", ["not json at all", '{"route": "weird", "query": ""}', "[]"])
async def test_bad_analysis_output_falls_back_to_rag_with_user_text(bad_output):
    graph, searcher = make_graph([bad_output], ["ok"], [POLICY_CHUNK])
    result = await run_chat(graph, "t5", SESSION, "giá S25?")
    assert result.route == "rag" and searcher.questions == ["giá S25?"]


async def test_state_is_kept_per_thread_and_documents_reset_each_turn():
    graph, _ = make_graph([analysis("rag"), analysis("chat")], ["Trong 7 ngày.", "Không có gì!"], [POLICY_CHUNK])
    first = await run_chat(graph, "t6", SESSION, "hoàn tiền mấy ngày?")
    second = await run_chat(graph, "t6", SESSION, "cảm ơn")
    assert first.sources and second.sources == []  # lượt chat không thừa hưởng tài liệu của lượt trước
    state = (await graph.aget_state({"configurable": {"thread_id": "t6"}})).values
    assert [m.type for m in state["messages"]] == ["human", "ai", "human", "ai"]
    other = (await graph.aget_state({"configurable": {"thread_id": "other"}})).values
    assert not other


async def test_long_conversation_is_summarized_and_trimmed():
    turns = 4
    graph, _ = make_graph([analysis("chat")] * turns + ["Khách hỏi về hoàn tiền."], ["ok"] * turns, policy=SummaryPolicy(6, 2))
    for i in range(turns):
        await run_chat(graph, "t7", SESSION, f"câu {i}")
    state = (await graph.aget_state({"configurable": {"thread_id": "t7"}})).values
    assert state["summary"] == "Khách hỏi về hoàn tiền."
    assert len(state["messages"]) <= 3 and state["messages"][0].type == "human"


async def test_stream_yields_reply_text_then_result():
    graph, _ = make_graph([analysis("rag")], ["Trong 7 ngày."], [POLICY_CHUNK])
    items = [item async for item in stream_chat(graph, "t8", SESSION, "hoàn tiền?")]
    assert "".join(i for i in items[:-1] if isinstance(i, str)) == "Trong 7 ngày."
    assert items[-1].route == "rag" and items[-1].sources[0]["source"].endswith("chinh-sach-hoan-tien.md")


def test_json_and_think_helpers():
    assert parse_json_object('```json\n{"route": "rag"}\n```') == {"route": "rag"}
    assert parse_json_object("no braces") is None
    assert message_text("<think>nghĩ...</think>Xin chào") == "Xin chào"
