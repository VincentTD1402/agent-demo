"""Spike (Plan A phase 1): danh tính ký theo từng lời gọi tool MCP.

Chứng minh với mcp 1.30 + langchain-mcp-adapters 0.3.2:
  1. Adapter đặt header theo từng lời gọi (tool interceptor) và MCP đọc được header trong tool.
  2. Token hết hạn / đổi tham số sau khi ký / phát lại / thiếu / sai khoá đều bị từ chối (fail-closed).
  3. Ký TẠI LÚC THỰC THI chịu được việc chờ lâu (khách xác nhận trễ), ký lúc LLM phát tool_call thì không.

Chạy: uv run --python 3.12 python backend/scripts/spike_mcp_identity.py
"""
import asyncio
import hashlib
import json
import logging
import socket
import threading
import time
import uuid

import jwt
import uvicorn
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.server.fastmcp import Context, FastMCP

KEY = "spike-context-key-" + "x" * 32
WRONG_KEY = "another-key-" + "y" * 32
TTL = 2  # giây; ngắn để thử chờ lâu
PORT = 18765
seen_jti: set[str] = set()


def args_hash(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sign(user_id: str, tool: str, args: dict, *, key: str = KEY, iat_offset: int = 0, jti: str | None = None) -> str:
    now = int(time.time()) + iat_offset
    claims = {"aud": "mcp", "user_id": user_id, "thread_id": "t-1", "tool": tool, "args_hash": args_hash(args),
              "jti": jti or uuid.uuid4().hex, "iat": now, "exp": now + TTL}
    return jwt.encode(claims, key, algorithm="HS256")


# ---------------- MCP server ----------------
mcp = FastMCP("spike", host="127.0.0.1", port=PORT, stateless_http=True)


def verify(ctx: Context, tool: str, args: dict) -> dict:
    """Fail-closed: mọi lỗi → từ chối. Danh tính chỉ lấy từ token đã verify."""
    token = ctx.request_context.request.headers.get("x-mcp-context")
    if not token:
        raise PermissionError("missing context")
    c = jwt.decode(token, KEY, algorithms=["HS256"], audience="mcp", options={"require": ["exp", "aud", "jti"]})
    if c["tool"] != tool or c["args_hash"] != args_hash(args):
        raise PermissionError("tool/args mismatch")
    if c["jti"] in seen_jti:
        raise PermissionError("replay")
    seen_jti.add(c["jti"])
    return c


@mcp.tool()
async def lookup_order(order_id: str, ctx: Context) -> dict:
    """Tra đơn (spike): trả về danh tính đã xác thực."""
    c = verify(ctx, "lookup_order", {"order_id": order_id})
    return {"order_id": order_id, "authenticated_user": c["user_id"], "thread": c["thread_id"]}


def run_server() -> None:
    uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1", port=PORT, log_level="error")).run()


# ---------------- client: interceptor ký lúc thực thi ----------------
MODE = {"name": "valid", "pre_signed": None}


async def signer(request, handler):
    mode, args = MODE["name"], request.args
    if mode == "no_header":
        return await handler(request)
    if mode == "pre_signed":  # token ký từ trước (lúc LLM phát tool_call) rồi dùng lại sau khi chờ
        token = MODE["pre_signed"]
    elif mode == "expired":
        token = sign("u-1", request.name, args, iat_offset=-3600)
    elif mode == "tampered_args":
        token = sign("u-1", request.name, {"order_id": "SOMETHING-ELSE"})
    elif mode == "wrong_key":
        token = sign("u-1", request.name, args, key=WRONG_KEY)
    elif mode == "replay":
        token = MODE.setdefault("replay_token", sign("u-1", request.name, args, jti="fixed-jti"))
    else:  # valid: ký NGAY lúc thực thi
        token = sign("u-1", request.name, args)
    return await handler(request.override(headers={"X-MCP-Context": token}))


async def call(tool, args) -> str:
    # Adapter 0.3.2 trả lỗi của tool dưới dạng nội dung "Error executing tool ..." (không ném ngoại lệ):
    # agent sẽ thấy lỗi như một ToolMessage; phía MCP vẫn đã từ chối thật.
    try:
        r = await tool.ainvoke(args)
    except Exception as e:  # noqa: BLE001
        return "REJECTED " + type(e).__name__
    text = json.dumps(r, ensure_ascii=False)
    return ("REJECTED " + text[text.find("Error executing") : text.find("Error executing") + 60]) if "Error executing tool" in text else "OK " + text[:90]


async def main() -> int:
    logging.disable(logging.INFO)
    threading.Thread(target=run_server, daemon=True).start()
    for _ in range(50):  # chờ server sẵn sàng thay vì sleep cố định
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                break
        except OSError:
            await asyncio.sleep(0.1)
    client = MultiServerMCPClient({"s": {"transport": "streamable_http", "url": f"http://127.0.0.1:{PORT}/mcp"}}, tool_interceptors=[signer])
    tool = (await client.get_tools())[0]
    schema_params = sorted(tool.args)  # tham số LLM nhìn thấy
    results = {}

    MODE["name"] = "valid"
    results["valid_signed_at_execution"] = await call(tool, {"order_id": "A101"})
    for name in ("no_header", "expired", "tampered_args", "wrong_key"):
        MODE["name"] = name
        results[name] = await call(tool, {"order_id": "A101"})
    MODE["name"] = "replay"
    results["replay_first"] = await call(tool, {"order_id": "A101"})
    results["replay_second"] = await call(tool, {"order_id": "A101"})

    # chờ lâu hơn TTL giữa lúc LLM phát tool_call và lúc thực thi (khách xác nhận trễ)
    early = sign("u-1", "lookup_order", {"order_id": "A101"})
    await asyncio.sleep(TTL + 1)
    MODE.update(name="pre_signed", pre_signed=early)
    results["signed_at_emission_then_waited"] = await call(tool, {"order_id": "A101"})
    MODE["name"] = "valid"
    results["signed_at_execution_after_waiting"] = await call(tool, {"order_id": "A101"})

    # Mỗi ca âm phải bị từ chối ĐÚNG LÝ DO (không chấp nhận lỗi mạng/server khác)
    expect_ok = {"valid_signed_at_execution", "replay_first", "signed_at_execution_after_waiting"}
    expect_reason = {"no_header": "missing context", "expired": "expired", "tampered_args": "mismatch",
                     "wrong_key": "Signature verification", "replay_second": "replay", "signed_at_emission_then_waited": "expired"}
    verdict = {}
    for k, v in results.items():
        if k in expect_ok:
            verdict[k] = v.startswith("OK") and '"authenticated_user' in v and "u-1" in v
        else:
            verdict[k] = v.startswith("REJECTED") and expect_reason[k] in v
    print(json.dumps({"llm_visible_tool_params": schema_params, "results": results, "as_expected": verdict}, ensure_ascii=False, indent=2))
    good = all(verdict.values()) and "ctx" not in schema_params
    print("SPIKE", "PASS" if good else "FAIL")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
