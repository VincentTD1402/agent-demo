#!/usr/bin/env bash
# Tạo .env từ .env.example và sinh khoá ngẫu nhiên (mật khẩu DB, khoá MCP, khoá nhân viên). Không ghi đè .env đã có.
# Dùng:  scripts/init-env.sh   rồi   docker compose up -d --build
set -eu
cd "$(dirname "$0")/.."
if [ -e .env ]; then echo ".env đã tồn tại: giữ nguyên (xoá file này nếu muốn tạo lại)"; exit 0; fi
rand() { if command -v openssl >/dev/null 2>&1; then openssl rand -hex 24; else head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; fi; }
cp .env.example .env
for key in POSTGRES_PASSWORD MCP_API_KEY STAFF_API_KEY AUTH_SECRET_KEY; do
  sed -i.bak "s|^${key}=.*|${key}=$(rand)|" .env
done
rm -f .env.bak
echo "Đã tạo .env với khoá ngẫu nhiên."
echo "Khoá nhân viên (đăng nhập /nhan-vien): $(grep '^STAFF_API_KEY=' .env | cut -d= -f2-)"
echo "Nếu LLM/embedding/reranker chạy ở địa chỉ khác, sửa các dòng *_API_URL trong .env."
