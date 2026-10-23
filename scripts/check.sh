#!/usr/bin/env bash
# Cổng kiểm tra chạy tay (chưa dùng CI): chạy trước mỗi mốc / mỗi lần merge.
# Dùng:  scripts/check.sh [--skip-audit] [--skip-frontend]
# Cần: uv, (tuỳ chọn) node/npm cho frontend, Docker cho test cần Postgres.
# Bắt buộc đặt TEST_DATABASE_URL hoặc ALEMBIC_DATABASE_URL; không có thì script THẤT BẠI trừ khi SKIP_DB_CHECKS=1.
set -u
cd "$(dirname "$0")/.."
SKIP_AUDIT=0; SKIP_FE=0; SKIPPED_DB=0
for a in "$@"; do case "$a" in --skip-audit) SKIP_AUDIT=1;; --skip-frontend) SKIP_FE=1;; esac; done
FAILED=()
run() { local name="$1"; shift; echo; echo "=== $name"; if "$@"; then echo "OK   $name"; else echo "FAIL $name"; FAILED+=("$name"); fi; }

if ! docker info >/dev/null 2>&1; then echo "CẢNH BÁO: Docker không chạy; test cần Postgres sẽ không thể chạy (Windows 11 Home cần WSL2)"; fi
run "backend lint (ruff)"  uv run --python 3.12 ruff check backend scripts
run "backend tests (pytest)" uv run --python 3.12 pytest -q
# alembic check cần Postgres đã migrate. ALEMBIC_DATABASE_URL (DSN role migrator) -> chạy trực tiếp;
# TEST_DATABASE_URL (superuser) -> test_migrations.py chạy alembic check trên DB tạm (đã nằm trong pytest ở trên).
if [ -n "${ALEMBIC_DATABASE_URL:-}" ]; then
  run "alembic check (model khớp migration)" bash -c 'cd backend && uv run --python 3.12 python -m alembic check'
elif [ -n "${TEST_DATABASE_URL:-}" ]; then
  echo "alembic check: đã chạy trong backend/tests/db/test_migrations.py"
elif [ "${SKIP_DB_CHECKS:-0}" = 1 ]; then
  SKIPPED_DB=1
  echo "!!! SKIPPED-DB-CHECKS: SKIP_DB_CHECKS=1, bỏ qua alembic check và test DB (không chặn được model lệch migration)"
else
  echo "FAIL: chưa đặt TEST_DATABASE_URL (Postgres pgvector) hay ALEMBIC_DATABASE_URL nên không chạy được alembic check và test DB."
  echo "      Đặt một trong hai, hoặc SKIP_DB_CHECKS=1 để cố ý bỏ qua (kết quả sẽ không được coi là đạt toàn bộ)."
  FAILED+=("thiếu cấu hình DB cho alembic check/test DB")
fi
if [ "$SKIP_AUDIT" = 0 ]; then run "pip-audit" uv run --python 3.12 python -m pip_audit; fi
if [ "$SKIP_FE" = 0 ] && [ -f frontend/package.json ]; then
  run "frontend typecheck" bash -c 'cd frontend && npm run --silent typecheck'
  if grep -q '"test"' frontend/package.json; then run "frontend tests" bash -c 'cd frontend && npm test --silent'; else echo "SKIP frontend tests (chưa có script test)"; fi
  if [ "$SKIP_AUDIT" = 0 ]; then run "npm audit (high)" bash -c 'cd frontend && npm audit --audit-level=high'; fi
fi

echo
if [ ${#FAILED[@]} -eq 0 ]; then
  if [ "$SKIPPED_DB" = 1 ]; then echo "!!! SKIPPED-DB-CHECKS: các bước còn lại đạt, NHƯNG alembic check và test DB CHƯA chạy (không phải TẤT CẢ ĐẠT)"; exit 0; fi
  echo "TẤT CẢ ĐẠT"; exit 0
fi
printf 'THẤT BẠI: %s\n' "${FAILED[@]}"; exit 1
