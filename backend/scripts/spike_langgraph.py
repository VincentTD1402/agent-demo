"""Spike (Plan A phase 1): các tính năng LangGraph 1.2 mà phase 6 dựa vào.

Cần một Postgres có pgvector. Ví dụ:
  docker run -d --rm --name spike-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t -p 55433:5432 pgvector/pgvector:pg17
  SPIKE_DATABASE_URL=postgresql://postgres:t@localhost:55433/t uv run --python 3.12 python backend/scripts/spike_langgraph.py
Kiểm tra: (a) context_schema phải truyền lại khi resume; (b) interrupt + Command async trên Postgres saver;
(c) saver/store dùng pool riêng; (d) store TTL + sweep (refresh_on_read=False); (e) stream_mode="messages" lọc theo node.
"""
import asyncio
import json
import os
import selectors
import uuid
from dataclasses import dataclass

from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.postgres import AsyncPostgresStore
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

URL = os.environ["SPIKE_DATABASE_URL"]


@dataclass
class Ctx:
    user_id: str


seen: dict = {}


def build(saver):
    def ask(state: MessagesState, runtime: Runtime[Ctx]):
        seen["before_interrupt"] = runtime.context.user_id if runtime.context else None
        decision = interrupt({"action": "request_refund"})
        # node chạy lại từ đầu sau resume: context có mặt hay không?
        seen["after_resume"] = runtime.context.user_id if runtime.context else None
        return {"messages": [AIMessage(f"decision={decision}")]}

    def answer(state: MessagesState):
        return {"messages": [AIMessage("final answer")]}

    g = StateGraph(MessagesState, context_schema=Ctx)
    g.add_node("ask", ask)
    g.add_node("answer", answer)
    g.add_edge(START, "ask")
    g.add_edge("ask", "answer")
    g.add_edge("answer", END)
    return g.compile(checkpointer=saver)


async def check_context_and_interrupt(pool) -> dict:
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    graph = build(saver)
    cfg = {"configurable": {"thread_id": uuid.uuid4().hex}}
    r1 = await graph.ainvoke({"messages": [("user", "hoàn tiền")]}, cfg, context=Ctx("u-1"))
    paused = "__interrupt__" in r1
    # resume KHÔNG truyền context
    await graph.ainvoke(Command(resume="approved"), cfg)
    ctx_without = seen["after_resume"]
    # resume CÓ truyền context
    cfg2 = {"configurable": {"thread_id": uuid.uuid4().hex}}
    await graph.ainvoke({"messages": [("user", "hoàn tiền")]}, cfg2, context=Ctx("u-2"))
    await graph.ainvoke(Command(resume="approved"), cfg2, context=Ctx("u-2"))
    ctx_with = seen["after_resume"]
    return {"interrupt_pauses": paused, "context_after_resume_without_passing": ctx_without,
            "context_after_resume_when_passed": ctx_with,
            "must_pass_context_on_resume": ctx_without is None and ctx_with == "u-2"}


async def check_ttl(pool) -> dict:
    store = AsyncPostgresStore(pool, ttl={"default_ttl": 0.02, "refresh_on_read": False, "sweep_interval_minutes": 1})
    await store.setup()
    ns = ("u-1", "memory")
    await store.aput(ns, "k", {"text": "preferred_brand=Apple"})
    before = await store.aget(ns, "k")
    await asyncio.sleep(2)  # 0.02 phút = 1,2 giây
    await store.sweep_ttl()
    after = await store.aget(ns, "k")
    return {"stored": before is not None, "gone_after_ttl_and_sweep": after is None,
            "sweeper_api": hasattr(store, "start_ttl_sweeper") and hasattr(store, "stop_ttl_sweeper")}


async def check_stream_by_node(pool) -> dict:
    saver = AsyncPostgresSaver(pool)

    def agent(state: MessagesState):
        return {"messages": [AIMessage("trả lời của agent")]}

    def guard(state: MessagesState):
        return {"messages": [AIMessage("đã qua guard")]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent)
    g.add_node("guard_output", guard)
    g.add_edge(START, "agent")
    g.add_edge("agent", "guard_output")
    g.add_edge("guard_output", END)
    graph = g.compile(checkpointer=saver)
    nodes = []
    async for mode, payload in graph.astream({"messages": [("user", "hi")]}, {"configurable": {"thread_id": uuid.uuid4().hex}}, stream_mode=["updates"]):
        nodes.extend(payload.keys())
    return {"update_events_by_node": nodes, "can_gate_on_guard_output": "guard_output" in nodes}


async def main() -> int:
    pool = AsyncConnectionPool(URL, min_size=1, max_size=4, open=False, kwargs={"autocommit": True, "row_factory": dict_row})
    await pool.open()
    out = {}
    for name, fn in (("context_and_interrupt", check_context_and_interrupt), ("store_ttl", check_ttl), ("stream_by_node", check_stream_by_node)):
        try:
            out[name] = await fn(pool)
        except Exception as e:  # noqa: BLE001
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    await pool.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ok = (out["context_and_interrupt"].get("must_pass_context_on_resume") and out["store_ttl"].get("gone_after_ttl_and_sweep")
          and out["stream_by_node"].get("can_gate_on_guard_output"))
    print("SPIKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())))
