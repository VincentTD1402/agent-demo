FROM python:3.12-slim

# uv: cài dependency nhanh, theo đúng uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/srv/.venv/bin:$PATH"

WORKDIR /srv

# Tách lớp dependency để cache khi chỉ đổi code
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
# Cấu hình + script migration Alembic (service `migrate` chạy `alembic upgrade head`)
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations

# Chạy bằng user thường, không dùng root
RUN useradd --system --uid 10001 appuser
# Thư mục ảnh sản phẩm nhân viên tải lên (mount volume product-images): chủ sở hữu là appuser để api ghi được
RUN mkdir -p /srv/uploads/products && chown -R appuser /srv/uploads
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
