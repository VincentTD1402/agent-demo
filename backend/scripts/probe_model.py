"""Probe năng lực model chat + embedding tự host (Plan A phase 1, cổng go/no-go).

Chạy:  uv run --python 3.12 python backend/scripts/probe_model.py [--runs 3]
Đọc cấu hình từ biến môi trường / file cấu hình của dự án; KHÔNG in hay ghi secret.
Ghi kết quả ra backend/scripts/probe-report.json và in tóm tắt.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from openai import OpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

GO_THRESHOLD = 0.95
REPORT = Path(__file__).with_name("probe-report.json")


class ProbeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    llm_base_url: str
    llm_api_key: str = "not-needed"
    llm_model: str
    embedding_model: str
    embedding_base_url: str = ""
    embedding_api_key: str = ""


LOOKUP_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": "Tra cứu đơn hàng theo mã đơn (chỉ đọc). Dùng khi khách hỏi trạng thái/chi tiết đơn.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "Mã đơn, ví dụ A101"}},
            "required": ["order_id"],
        },
    },
}
ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["product_advice", "order_support", "refund", "policy_faq", "human_handoff", "out_of_scope"]},
        "lang": {"type": "string", "enum": ["vi", "en"]},
        "confidence": {"type": "number"},
    },
    "required": ["label", "lang", "confidence"],
    "additionalProperties": False,
}
SYSTEM = (
    "Bạn là nhân viên chăm sóc khách hàng của cửa hàng điện thoại. Trả lời ngắn gọn. "
    "Always reply in the same language as the customer's LAST message: English question -> English answer, "
    "Vietnamese question -> Vietnamese answer."
)
# Model tự host là loại "thinking": mặc định suy luận lộ vào `content`. Phải tắt ở mọi lời gọi chat.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
ROUTER_SYSTEM = (
    "Phân loại ý định của khách. Chỉ trả JSON theo schema. Nhãn: product_advice (tư vấn chọn sản phẩm), "
    "order_support (tra cứu/hỏi trạng thái đơn), refund (muốn hoàn tiền/trả hàng), policy_faq (hỏi chính sách), "
    "human_handoff (yêu cầu gặp nhân viên), out_of_scope (ngoài phạm vi)."
)


def has_vietnamese(text: str) -> bool:
    return any(ch in text for ch in "ăâđêôơưáàảãạéèẻẽẹíìỉĩịóòỏõọúùủũụýỳỷỹỵ")


def tool_call(client, model, user, **kw):
    r = client.chat.completions.create(
        model=model, temperature=0, tools=[LOOKUP_TOOL], extra_body=NO_THINK,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], **kw,
    )
    return r.choices[0].message


def s_tool_single(c, m):
    msg = tool_call(c, m, "Đơn A101 của tôi đến đâu rồi?")
    calls = msg.tool_calls or []
    ok = len(calls) == 1 and calls[0].function.name == "lookup_order" and json.loads(calls[0].function.arguments).get("order_id", "").upper() == "A101"
    return ok, "1 tool call lookup_order(A101)"


def s_tool_parallel(c, m):
    msg = tool_call(c, m, "Kiểm tra giúp tôi cả đơn A100 và đơn B200.")
    ids = {json.loads(t.function.arguments).get("order_id", "").upper() for t in (msg.tool_calls or [])}
    return {"A100", "B200"} <= ids, f"order_id gọi: {sorted(ids)}"


def s_tool_choice_forced(c, m):
    msg = tool_call(c, m, "Xin chào", tool_choice={"type": "function", "function": {"name": "lookup_order"}})
    return bool(msg.tool_calls), "tool_choice ép gọi tool"


def s_no_tool_needed(c, m):
    msg = tool_call(c, m, "Cảm ơn bạn nhé!")
    return not msg.tool_calls and bool(msg.content), "không gọi tool khi chỉ cảm ơn"


def s_structured_json_schema(c, m):
    r = c.chat.completions.create(
        model=m, temperature=0, extra_body=NO_THINK,
        messages=[{"role": "system", "content": ROUTER_SYSTEM},
                  {"role": "user", "content": "Tôi muốn hoàn tiền đơn A100 vì máy lỗi"}],
        response_format={"type": "json_schema", "json_schema": {"name": "router", "schema": ROUTER_SCHEMA, "strict": True}},
    )
    d = json.loads(r.choices[0].message.content)
    return d.get("label") == "refund" and d.get("lang") == "vi", f"{d}"


def s_structured_json_object(c, m):
    r = c.chat.completions.create(
        model=m, temperature=0, extra_body=NO_THINK, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": 'Trả JSON dạng {"label":"...","lang":"vi|en","confidence":0-1}. label thuộc: product_advice, order_support, refund, policy_faq, human_handoff, out_of_scope.'},
                  {"role": "user", "content": "Where is my order A101?"}],
    )
    d = json.loads(r.choices[0].message.content)
    return d.get("label") == "order_support" and d.get("lang") == "en", f"{d}"


def s_lang_en(c, m):
    r = c.chat.completions.create(model=m, temperature=0, extra_body=NO_THINK, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": "What is your return policy for phones?"}])
    t = r.choices[0].message.content or ""
    return bool(t) and not has_vietnamese(t), t[:80]


def s_lang_vi(c, m):
    r = c.chat.completions.create(model=m, temperature=0, extra_body=NO_THINK, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Chính sách đổi trả điện thoại của shop thế nào?"}])
    t = r.choices[0].message.content or ""
    return has_vietnamese(t), t[:80]


def s_thinking_clean(c, m):
    r = c.chat.completions.create(model=m, temperature=0, extra_body=NO_THINK, messages=[{"role": "user", "content": "Chào bạn"}])
    t = (r.choices[0].message.content or "").strip()
    return bool(t) and not t.startswith("Thinking Process"), t[:80]


def default_thinking_leak(c, m) -> dict:
    """Thông tin (không tính điểm): gọi KHÔNG tắt thinking để ghi nhận hành vi mặc định."""
    r = c.chat.completions.create(model=m, temperature=0, messages=[{"role": "user", "content": "Chào bạn"}])
    t = (r.choices[0].message.content or "").strip()
    return {"leaks_reasoning_into_content": t.startswith("Thinking Process"), "sample": t[:60]}


def s_mixed_language(c, m):
    r = c.chat.completions.create(
        model=m, temperature=0, extra_body=NO_THINK, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": 'Trả JSON {"label":"...","lang":"vi|en"}. label thuộc: product_advice, order_support, refund, policy_faq, human_handoff, out_of_scope. lang là ngôn ngữ chính của câu.'},
                  {"role": "user", "content": "Cho mình hỏi warranty của iPhone 16 là bao lâu vậy?"}],
    )
    d = json.loads(r.choices[0].message.content)
    return d.get("label") == "policy_faq" and d.get("lang") in ("vi", "en"), f"{d}"


def s_streaming(c, m):
    start, first, n = time.perf_counter(), None, 0
    for chunk in c.chat.completions.create(model=m, temperature=0, stream=True, extra_body=NO_THINK, messages=[{"role": "user", "content": "Đếm từ 1 đến 20."}]):
        if chunk.choices and chunk.choices[0].delta.content:
            first = first or time.perf_counter() - start
            n += 1
    return n > 3, f"{n} chunk, ttfb {first and round(first, 2)}s"


SCENARIOS = {
    "tool_single": ("tool_calling", s_tool_single),
    "tool_parallel": ("tool_calling", s_tool_parallel),
    "tool_choice_forced": ("tool_calling", s_tool_choice_forced),
    "no_tool_needed": ("tool_calling", s_no_tool_needed),
    "structured_json_schema": ("structured_output", s_structured_json_schema),
    "structured_json_object": ("structured_output", s_structured_json_object),
    "lang_en": ("language", s_lang_en),
    "lang_vi": ("language", s_lang_vi),
    "mixed_language_router": ("language", s_mixed_language),
    "thinking_clean": ("thinking", s_thinking_clean),
    "streaming": ("streaming", s_streaming),
}


def probe_embedding(s: ProbeSettings) -> dict:
    ec = OpenAI(base_url=s.embedding_base_url or s.llm_base_url, api_key=s.embedding_api_key or s.llm_api_key)
    out: dict = {"model": s.embedding_model}
    try:
        v = ec.embeddings.create(model=s.embedding_model, input=["Xin chào, tôi muốn hoàn tiền đơn hàng"]).data[0].embedding
        out["dims"] = len(v)
        out["vietnamese_ok"] = True
    except Exception as e:  # noqa: BLE001
        out["vietnamese_ok"] = False
        out["error"] = type(e).__name__ + ": " + str(e)[:160]
    try:
        ec.embeddings.create(model=s.embedding_model, input=["từ " * 3000])
        out["over_limit"] = "không lỗi (server tự cắt hoặc chấp nhận)"
    except Exception as e:  # noqa: BLE001
        out["over_limit"] = f"lỗi: {type(e).__name__} status={getattr(e, 'status_code', None)}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5, help="số lần chạy mỗi kịch bản (temperature 0 nên các lần gần giống nhau; mẫu nhỏ, ngưỡng chỉ mang tính chặn lỗi nặng)")
    args = ap.parse_args()
    s = ProbeSettings()  # type: ignore[call-arg]
    client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=90)
    try:
        served = [m.id for m in client.models.list().data]
    except Exception as e:  # noqa: BLE001
        served = [f"lỗi {type(e).__name__}"]

    results: dict = {}
    latencies: list[float] = []
    for name, (group, fn) in SCENARIOS.items():
        trials = []
        for _ in range(args.runs):
            t0 = time.perf_counter()
            try:
                ok, note = fn(client, s.llm_model)
            except Exception as e:  # noqa: BLE001
                ok, note = False, f"{type(e).__name__}: {str(e)[:120]}"
            latencies.append(time.perf_counter() - t0)
            trials.append({"ok": bool(ok), "note": note})
        results[name] = {"group": group, "pass_rate": sum(t["ok"] for t in trials) / len(trials), "trials": trials}
        print(f"{name:24} {results[name]['pass_rate']:.0%}")

    groups: dict[str, list[float]] = {}
    for r in results.values():
        groups.setdefault(r["group"], []).append(r["pass_rate"])
    group_rates = {g: round(sum(v) / len(v), 3) for g, v in groups.items()}
    overall = round(sum(r["pass_rate"] for r in results.values()) / len(results), 3)
    emb = probe_embedding(s)
    verdict = {
        "overall_pass_rate": overall,
        "threshold": GO_THRESHOLD,
        # plan yêu cầu TỪNG nhóm đạt ngưỡng, không chỉ trung bình chung
        "go": all(v >= GO_THRESHOLD for v in group_rates.values()) and overall >= GO_THRESHOLD and emb.get("dims") == 1024,
        "structured_output_mode": "json_schema" if results["structured_json_schema"]["pass_rate"] >= GO_THRESHOLD
        else ("json_object" if results["structured_json_object"]["pass_rate"] >= GO_THRESHOLD else "parse_from_text"),
    }
    report = {
        "llm_host": urlparse(s.llm_base_url).netloc,
        "llm_model": s.llm_model,
        "models_served": served[:10],
        "runs_per_scenario": args.runs,
        "group_pass_rates": group_rates,
        "latency_seconds": {"p50": round(statistics.median(latencies), 2), "max": round(max(latencies), 2)},
        "embedding": emb,
        "required_request_flags": {"extra_body": NO_THINK},
        "default_behaviour": default_thinking_leak(client, s.llm_model),
        "verdict": verdict,
        "scenarios": results,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("group_pass_rates", "latency_seconds", "embedding", "required_request_flags", "default_behaviour", "verdict")}, ensure_ascii=False, indent=2))
    return 0 if verdict["go"] else 1


if __name__ == "__main__":
    sys.exit(main())
