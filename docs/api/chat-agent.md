# Chat agent (LangGraph RAG)

Agent trả lời khách ShopMobile dựa trên tài liệu đã nạp (xem `document-ingestion.md`). Hai chế độ: RAG (chính sách, kiến thức chung) và nhánh `shop` dùng tool qua MCP (giá/tồn kho thật, giỏ hàng, đặt hàng, thanh toán, tra đơn, yêu cầu hoàn tiền; xem `shop-orders-mcp-and-staff.md`).

## Luồng

```
START -> analyze --chat---------------> chat ----------+
                 --out_of_scope--------> decline -------+--> summarize (khi hội thoại dài) -> END
                 --rag--> retrieve --có tài liệu--> generate --+
                                   --không có-----> decline ---+
                 --shop--> shop_agent <--> tools   (lặp tới khi model trả lời)
```

- `analyze` (LLM, JSON): chọn nhánh `chat` | `rag` | `shop` | `out_of_scope` và viết lại tin nhắn cuối thành câu hỏi độc lập (giải nghĩa "nó", "còn bản kia?"). Lỗi hoặc JSON sai thì mặc định nhánh `rag` với nguyên văn tin nhắn.
- `retrieve`: embedding câu hỏi (kèm Instruct của Qwen3) -> pgvector cosine top `RAG_TOP_K` -> rerank (Qwen3-Reranker) -> giữ tối đa `RAG_TOP_N` đoạn có điểm >= `RAG_MIN_SCORE`.
- `generate`: trả lời chỉ dựa trên các đoạn tìm được, cùng ngôn ngữ với khách. Không có đoạn nào đủ điểm thì sang `decline` (báo chưa có thông tin, gợi ý liên hệ nhân viên), không bịa.
- `shop_agent` + `tools`: vòng lặp gọi tool (tối đa ~9 lượt, vượt thì dừng và xin lỗi). `session_id` do server gắn vào tool, model không điền được. Tool MCP nạp lười, thử lại mỗi 30 giây nếu MCP server chưa lên; trong lúc đó câu hỏi mua sắm đi nhánh RAG. Tin nhắn tool_call dở dang (lỗi giữa chừng) được gỡ ở đầu lượt kế tiếp.
- `summarize`: quá `RAG_SUMMARIZE_AFTER` tin nhắn thì tóm tắt phần cũ, giữ `RAG_KEEP_MESSAGES` tin gần nhất.
- Hội thoại lưu bằng `AsyncPostgresSaver` theo `thread_id` (bảng `checkpoint*`, tạo tự động lần dùng đầu).

## Endpoint

| Endpoint | Mô tả |
|---|---|
| `POST /chat` | `{"message": "...", "thread_id": "tuỳ chọn", "session_id": "tuỳ chọn"}` -> `{thread_id, reply, route, sources[{source, score}]}` |
| `POST /chat/stream` | cùng body, SSE: `{"type":"token","content":...}` nhiều lần, rồi `{"type":"done", thread_id, reply, route, sources}`; lỗi giữa chừng: `{"type":"error"}` |
| `DELETE /chat/{thread_id}` | xoá hội thoại |

- `session_id` (16-64 ký tự `[A-Za-z0-9_-]`) là khoá giỏ hàng/đơn của trình duyệt; bỏ trống thì dùng `thread_id`. Bỏ trống `thread_id` thì server sinh UUID mới; client gửi lại giá trị đó để tiếp tục hội thoại. `thread_id` khớp `[A-Za-z0-9_-]{8,64}`; `message` 1-2000 ký tự.
- Nếu đặt `API_KEY` thì cần header `X-API-Key`. Lỗi embedding/rerank/LLM/DB trả 502; agent chưa khởi tạo xong trả 503.

## Guardrail và giọng tư vấn

Chỉ phục vụ việc của shop, chống spam và hỏi ngoài lề, theo ba lớp (code ở `app/agent/guardrails.py`, `nodes.py`, `prompts.py`):

1. **Trước khi gọi model** (không tốn token, không thể thương lượng):
   - Giới hạn tần suất trong bộ nhớ: `CHAT_RATE_PER_MINUTE` / `CHAT_RATE_PER_HOUR` mỗi phiên, `CHAT_RATE_PER_IP_PER_MINUTE` mỗi IP (nginx đặt `X-Forwarded-For`), cùng nội dung gửi lặp quá `CHAT_DUPLICATE_LIMIT` lần/phút. Vượt thì HTTP 429 kèm `Retry-After`. Tin bị chặn vẫn tính vào hạn mức.
   - Tin rỗng/toàn ký tự, lặp ký tự hoặc lặp từ, từ 3 link trở lên, và câu tiêm lệnh ("bỏ qua hướng dẫn", "system prompt", "đóng vai"...) nhận câu trả lời dựng sẵn, không vào hội thoại và không gọi agent.
2. **Phân loại**: câu không liên quan shop (thời tiết, code, dịch thuật, chuyện phiếm, tư vấn sức khoẻ/pháp lý/đầu tư...) đi nhánh `out_of_scope` và được từ chối nhẹ nhàng, gợi ý việc shop có thể giúp. Hỏi ngoài lề liên tiếp: từ lượt 3 từ chối ngắn gọn dứt khoát, từ lượt 5 trả câu dựng sẵn không gọi model; một câu đúng việc đặt lại bộ đếm.
3. **Prompt**: mọi câu trả lời gửi khách mang persona nhân viên tư vấn ("em" gọi khách "anh/chị", mở đầu "Dạ", lắng nghe rồi trả lời và gợi ý bước tiếp, không đề nghị việc ngoài khả năng như giữ máy/giảm giá) và quy tắc phạm vi (không đổi vai, không lộ hướng dẫn).

Bộ đếm tần suất nằm trong bộ nhớ một tiến trình: chạy nhiều replica api thì mỗi replica đếm riêng. Khoá dò đơn và giới hạn số đơn nằm trong DB (xem `shop-orders-mcp-and-staff.md`).

## Cấu hình

`LLM_API_URL`, `LLM_MODEL_NAME`, `RERANKER_API_URL`, `RERANKER_MODEL_NAME`, `MCP_SERVER_URL`, `MCP_API_KEY` (xem `.env.example`) và nhóm `RAG_*`. Các bước nội bộ (phân loại, tóm tắt) dùng nhiệt độ 0; câu trả lời dùng `RAG_ANSWER_TEMPERATURE`. Qwen3 chạy với `enable_thinking=false`.

Lưu ý khi chạy trên Windows ngoài Docker: psycopg async cần `SelectorEventLoop` (đặt `asyncio.WindowsSelectorEventLoopPolicy()`); trong Docker (Linux) không cần.

## Code

`backend/app/agent/`: `state.py`, `prompts.py`, `llm.py`, `reranker_client.py`, `retrieval.py`, `nodes.py`, `graph.py`, `shop_tools.py`, `runner.py`, `router.py`, `bootstrap.py`. Test: `test_agent_graph.py`, `test_agent_shop_branch.py` (model/tool giả, không cần mạng/DB).
