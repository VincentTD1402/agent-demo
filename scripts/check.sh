#!/usr/bin/env bash
# Cổng kiểm tra chạy tay (chưa dùng CI): chạy trước mỗi mốc / mỗi lần merge.
# Dùng:  scripts/check.sh [--skip-audit] [--skip-frontend]
# Cần: uv, (tuỳ chọn) node/npm cho frontend, Docker cho test cần Postgres.
set -u
cd "$(dirname "$0")/.."
SKIP_AUDIT=0; SKIP_FE=0
for a in "$@"; do case "$a" in --skip-audit) SKIP_AUDIT=1;; --skip-frontend) SKIP_FE=1;; esac; done
FAILED=()
run() { local name="$1"; shift; echo; echo "=== $name"; if "$@"; then echo "OK   $name"; else echo "FAIL $name"; FAILED+=("$name"); fi; }

if ! docker info >/dev/null 2>&1; then echo "CẢNH BÁO: Docker không chạy; test cần Postgres sẽ không thể chạy (Windows 11 Home cần WSL2)"; fi
run "backend lint (ruff)"  uv run --python 3.12 ruff check backend scripts
run "backend tests (pytest)" uv run --python 3.12 pytest -q
if [ -f backend/alembic.ini ]; then
  run "alembic check (model khớp migration)" bash -c 'cd backend && uv run --python 3.12 alembic check'
else
  echo "SKIP alembic check (chưa có backend/alembic.ini)"
fi
if [ "$SKIP_AUDIT" = 0 ]; then run "pip-audit" uv run --python 3.12 python -m pip_audit; fi
if [ "$SKIP_FE" = 0 ] && [ -f frontend/package.json ]; then
  run "frontend typecheck" bash -c 'cd frontend && npm run --silent typecheck'
  if grep -q '"test"' frontend/package.json; then run "frontend tests" bash -c 'cd frontend && npm test --silent'; else echo "SKIP frontend tests (chưa có script test)"; fi
  if [ "$SKIP_AUDIT" = 0 ]; then run "npm audit (high)" bash -c 'cd frontend && npm audit --audit-level=high'; fi
fi

echo
if [ ${#FAILED[@]} -eq 0 ]; then echo "TẤT CẢ ĐẠT"; exit 0; fi
printf 'THẤT BẠI: %s\n' "${FAILED[@]}"; exit 1
