# Chat agent (LangGraph RAG)

Agent trả lời khách ShopMobile dựa trên tài liệu đã nạp (xem `document-ingestion.md`). Chưa có tool/MCP: chỉ RAG; agent không tra đơn, không tạo yêu cầu hoàn tiền.

## Luồng

```
START -> analyze --chat---------------> chat ----------+
                 --out_of_scope--------> decline -------+--> summarize (khi hội thoại dài) -> END
                 --rag--> retrieve --có tài liệu--> generate --+
                                   --không có-----> decline ---+
```

- `analyze` (LLM, JSON): chọn nhánh `chat` | `rag` | `out_of_scope` và viết lại tin nhắn cuối thành câu hỏi độc lập (giải nghĩa "nó", "còn bản kia?"). Lỗi hoặc JSON sai thì mặc định nhánh `rag` với nguyên văn tin nhắn.
- `retrieve`: embedding câu hỏi (kèm Instruct của Qwen3) -> pgvector cosine top `RAG_TOP_K` -> rerank (Qwen3-Reranker) -> giữ tối đa `RAG_TOP_N` đoạn có điểm >= `RAG_MIN_SCORE`.
- `generate`: trả lời chỉ dựa trên các đoạn tìm được, cùng ngôn ngữ với khách. Không có đoạn nào đủ điểm thì sang `decline` (báo chưa có thông tin, gợi ý liên hệ nhân viên), không bịa.
- `summarize`: quá `RAG_SUMMARIZE_AFTER` tin nhắn thì tóm tắt phần cũ, giữ `RAG_KEEP_MESSAGES` tin gần nhất.
- Hội thoại lưu bằng `AsyncPostgresSaver` theo `thread_id` (bảng `checkpoint*`, tạo tự động lần dùng đầu).

## Endpoint

| Endpoint | Mô tả |
|---|---|
| `POST /chat` | `{"message": "...", "thread_id": "tuỳ chọn"}` -> `{thread_id, reply, route, sources[{source, score}]}` |
| `POST /chat/stream` | cùng body, SSE: `{"type":"token","content":...}` nhiều lần, rồi `{"type":"done", thread_id, reply, route, sources}`; lỗi giữa chừng: `{"type":"error"}` |
| `DELETE /chat/{thread_id}` | xoá hội thoại |

- Bỏ trống `thread_id` thì server sinh UUID mới; client gửi lại giá trị đó để tiếp tục hội thoại. `thread_id` khớp `[A-Za-z0-9_-]{8,64}`; `message` 1-2000 ký tự.
- Nếu đặt `API_KEY` thì cần header `X-API-Key`. Lỗi embedding/rerank/LLM/DB trả 502; agent chưa khởi tạo xong trả 503.

## Cấu hình

`LLM_API_URL`, `LLM_MODEL_NAME`, `RERANKER_API_URL`, `RERANKER_MODEL_NAME` (xem `.env.example`) và nhóm `RAG_*`. Các bước nội bộ (phân loại, tóm tắt) dùng nhiệt độ 0; câu trả lời dùng `RAG_ANSWER_TEMPERATURE`. Qwen3 chạy với `enable_thinking=false`.

Lưu ý khi chạy trên Windows ngoài Docker: psycopg async cần `SelectorEventLoop` (đặt `asyncio.WindowsSelectorEventLoopPolicy()`); trong Docker (Linux) không cần.

## Code

`backend/app/agent/`: `state.py`, `prompts.py`, `llm.py`, `reranker_client.py`, `retrieval.py`, `nodes.py`, `graph.py`, `runner.py`, `router.py`, `bootstrap.py`. Test: `backend/tests/test_agent_graph.py` (LLM giả, không cần mạng/DB).
