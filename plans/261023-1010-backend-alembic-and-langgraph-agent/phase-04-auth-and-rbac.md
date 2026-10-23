---
phase: 4
title: "Auth and RBAC"
status: pending
priority: P1
effort: "5d"
milestone: "M1"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#3"]
---

# Phase 4: Auth and RBAC

## Overview

Đăng nhập thật: đăng ký/đăng nhập cho khách, tài khoản nhân viên tạo bằng CLI, JWT + refresh token xoay vòng, phân quyền theo vai trò. Gỡ hẳn cơ chế `API_KEY`.

## Requirements

- Functional: register, login, refresh, logout, me, đổi mật khẩu; vai trò `customer`/`staff`/`admin`; dependency `require_role`.
- Non-functional: mật khẩu argon2id; không lộ tài khoản tồn tại hay không; thu hồi quyền có hiệu lực ngay; thiếu/yếu secret thì không khởi động.

## Architecture

- **Access token** JWT HS256 (`JWT_SECRET`), hạn 15 phút, claim `sub`, `tv` (token_version), `iss`, `aud`, `exp`; verify ghim thuật toán, bắt buộc `iss/aud/exp`. Nâng RS256/JWKS khi có IdP (ghi docs). Không dùng `jti`.
- **Quyền không lấy từ claim:** mọi route đặc quyền (và `current_user`) tải `role`, `is_active`, `token_version` từ DB; đổi mật khẩu/vô hiệu hoá/hạ quyền tăng `token_version` nên token cũ chết ngay.
- **Refresh token** ngẫu nhiên 256 bit, lưu hash, hạn 14 ngày, xoay vòng theo `family_id`. **Ân hạn 10-30 giây**: dùng lại token vừa bị xoay trong cửa sổ này trả về token kế nhiệm thay vì thu hồi (tránh đăng xuất oan khi 2 tab/2 request song song); ngoài cửa sổ mà tái dùng → thu hồi cả họ.
- Cookie refresh: `HttpOnly; Secure; SameSite=Lax` qua cùng origin (nginx `/api`); yêu cầu header tuỳ chỉnh cho refresh/logout chống CSRF. Tài liệu hoá HTTPS + HSTS (cookie `Secure` bị bỏ qua trên HTTP, trừ localhost khi dev).
- **Đăng ký công khai chỉ tạo `customer`**; `RegisterRequest` cấm field thừa (`extra=forbid`). Staff/admin chỉ tạo bằng CLI `python -m app.auth.create_staff` (admin đầu tiên cũng vậy); không có admin API.
- **Giới hạn đăng nhập sai:** một module rate-limit dùng chung (cũng dùng cho chat ở phase 7), bộ đếm lưu Postgres (nhiều worker, sống qua restart), khoá theo IP + email, **làm chậm dần** thay vì khoá cứng, không khoá nhân viên chỉ theo email. IP thật lấy từ header do nginx ghi đè, uvicorn chỉ tin nginx.
- **Settings fail-closed:** `JWT_SECRET` < 32 byte ngẫu nhiên hoặc là giá trị mẫu → app không khởi động; `MCP_CONTEXT_KEY` thiếu → không khởi động.
- Gỡ `API_KEY` / `require_api_key` / `X-API-Key` ở nginx và CORS; route công khai là catalog `GET /v1/products*`, `/health`; mọi route khác cần JWT.
- **Vô hiệu hoá tài khoản:** CLI `python -m app.auth.set_active <email> --off` tăng `token_version` (cơ chế để test "vô hiệu hoá nhân viên"). `admin` v1 không có màn hình riêng: quyền như staff, chỉ khác ở việc được tạo/vô hiệu hoá bằng CLI.
- Ngoài phạm vi: email xác minh, quên mật khẩu (cần SMTP), MFA, xoá tài khoản/xuất dữ liệu (ghi vào roadmap).

## Related Code Files

- Create: `backend/app/auth/{passwords,tokens,service,deps,schemas,cli}.py`, `backend/app/api/routes_auth.py`, `backend/app/api/rate_limit.py`, `backend/tests/auth/*`
- Modify: `backend/app/api/deps.py` (xoá `require_api_key`, thêm `current_user`), `backend/app/api/{routes_chat,routes_products}.py` (bỏ dependency API key), `backend/app/main.py` (CORS thêm `Authorization`, bỏ `X-API-Key`), `backend/app/settings/api.py`, `docker-compose.yml`/`.env.example` (bỏ `API_KEY`, thêm secret), `frontend/nginx.conf.template` (bỏ `X-API-Key`; ghi đè `X-Forwarded-For`), `pyproject.toml`
- Delete: `require_api_key` và mọi tham chiếu

## Implementation Steps

1. `passwords.py` (argon2id + chính sách: tối thiểu 10 ký tự, chặn danh sách mật khẩu phổ biến nhỏ); `tokens.py` (access, refresh + ân hạn, `token_version`).
2. `service.py`: register/login (thời gian hằng, lỗi chung), refresh, logout (thu hồi họ), đổi mật khẩu (tăng `token_version`, thu hồi mọi refresh).
3. `rate_limit.py` Postgres-backed, làm chậm dần; middleware lấy IP tin cậy.
4. `deps.py`: `current_user`, `require_role` đọc từ DB.
5. CLI tạo staff/admin; seed staff demo chỉ khi `ENV=dev`.
6. Gỡ `API_KEY` ở backend, compose, nginx, CORS, `.env.example`; cập nhật test hiện có dùng API key.
7. `pip-audit` nằm trong `scripts/check` từ phase này; lock mới được rà.
8. Test: đăng ký trùng email, sai mật khẩu, token hết hạn/giả mạo/sai alg, refresh song song trong ân hạn, tái dùng ngoài ân hạn thu hồi cả họ, khách gọi route staff = 403, nhân viên bị vô hiệu hoá mất quyền ngay, đăng ký với `role=admin` bị từ chối, secret yếu không khởi động.

## Todo List

- [ ] Mật khẩu argon2id + chính sách
- [ ] JWT + `token_version` + refresh xoay vòng có ân hạn
- [ ] Rate limit Postgres-backed + IP tin cậy
- [ ] `current_user`/`require_role` đọc DB + CLI staff/set_active
- [ ] Gỡ `API_KEY` toàn repo + `pip-audit` trong `scripts/check`

## Success Criteria

- [ ] Không còn `API_KEY`, `require_api_key`, `X-API-Key` ở bất kỳ đâu (grep sạch)
- [ ] Vô hiệu hoá nhân viên → mọi token cũ bị từ chối ngay lập tức
- [ ] Mở 2 tab cùng lúc không làm đăng xuất; tái dùng token ngoài ân hạn thì thu hồi cả họ
- [ ] Khách không tự tạo/nâng quyền staff được

## Risk Assessment

Tự xây auth dễ sai chi tiết → bám các bước trên, test tấn công cơ bản, rà soát bằng `code-reviewer` + `security-scan` ở phase 9. Lộ `JWT_SECRET` = giả mạo mọi vai trò → chỉ qua env/secret, runbook xoay vòng (đổi secret = mọi access token chết, refresh vẫn dùng lại được).

## Security Considerations

Quyền đọc từ DB, thu hồi tức thì, secret fail-closed, đăng ký cấm field thừa, cookie HttpOnly + kiểm Origin, không còn cơ chế API key.

## Next Steps

Phase 7 dùng `current_user`/`require_role`; Plan B phase 1 dựng frontend đăng nhập dựa trên cookie/refresh ở đây.
