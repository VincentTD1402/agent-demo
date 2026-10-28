# Document ingestion API

Nạp tài liệu vào Postgres/pgvector: trích văn bản -> chia chunk -> embedding -> lưu `documents` + `chunks` (migration `0002`).

Định dạng: `.txt`, `.md`, `.pdf` (cần có text, không OCR), `.docx` (đổi sang Markdown: heading, list, bảng). `.md`/`.docx` chia chunk theo heading (`#`..`###`) rồi theo `EMBEDDING_CHUNK_SIZE`/`EMBEDDING_CHUNK_OVERLAP`; chunk tiếp theo của một mục được gắn lại đường dẫn heading.

Nếu đặt `API_KEY` thì mọi endpoint dưới đây cần header `X-API-Key`.

| Endpoint | Mô tả |
|----------|-------|
| `POST /documents/upload` | multipart: `files` (nhiều file), `language` (tuỳ chọn `vi`\|`ko`) |
| `POST /documents/ingest-folder` | JSON `{"subfolder": "", "recursive": true, "language": null}`; quét `DOCUMENTS_DIR` (Docker: mount `./documents`), không cho thoát khỏi thư mục này |
| `DELETE /documents?source=<tên>` | xoá tài liệu + chunk |

Mỗi file có kết quả riêng trong `results[]`: `indexed` | `unchanged` (nội dung + language không đổi, không gọi embedding) | `skipped` (sai định dạng, quá `MAX_UPLOAD_MB`, không có text...) | `failed` (embedding/DB lỗi). Lỗi từng file không làm hỏng cả batch.

`source` = tên file (upload) hoặc đường dẫn tương đối (folder). Nạp lại cùng `source` thì thay toàn bộ chunk trong một transaction. Quá `MAX_CONCURRENT_UPLOADS` lượt chạy đồng thời -> 429.

`EMBEDDING_API_URL` nhận cả dạng base (`.../v1`) lẫn đầy đủ (`.../v1/embeddings`); vector cố định 1024 chiều.

```
curl -F files=@faq.docx -F language=vi http://localhost:8000/documents/upload
curl -X POST http://localhost:8000/documents/ingest-folder -H 'Content-Type: application/json' -d '{"subfolder":"policies"}'
```
