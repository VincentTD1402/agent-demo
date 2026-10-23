---
phase: 1
title: "Frontend auth"
status: pending
priority: P1
effort: "2.5d"
milestone: "M1"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#4"]
---

# Phase 1: Frontend auth

## Overview

Đăng nhập/đăng ký trên storefront, giữ phiên an toàn, chặn route theo vai trò, dọn sạch trạng thái khi đăng xuất. Dựng luôn hạ tầng test frontend (hiện chưa có). Bỏ ô "Khách" tự gõ và API key trong nginx.

## Requirements

- Functional: trang đăng nhập/đăng ký, menu tài khoản, đăng xuất, route guard cho khách và nhân viên; chat yêu cầu đăng nhập.
- Non-functional: access token chỉ trong bộ nhớ; refresh token ở cookie HttpOnly; form có nhãn, lỗi cạnh trường, trạng thái loading; **tải lại trang giữ phiên qua nginx thật**.

## Architecture

- `AuthProvider` giữ `{user, accessToken}`; khi tải trang gọi `POST /v1/auth/refresh` (cookie) để khôi phục phiên. Refresh **single-flight** ở client; server có ân hạn 10-30 giây (Plan A phase 4).
- `api.ts` thành client dùng chung: gắn `Authorization`, 401 thì refresh một lần rồi thử lại, hết hạn thì về trang đăng nhập; mọi lời gọi đi qua `/api`. Xử lý 409 thành lỗi có kiểu (không còn "Lỗi 409" chung chung).
- **Cookie qua nginx:** backend đặt cookie `Path=/` (hoặc `proxy_cookie_path` ánh xạ) để trình duyệt gửi lại qua tiền tố `/api`; `SameSite=Lax` + kiểm tra header `Origin`/`X-Requested-With` cho `/v1/auth/refresh`/`logout`; cờ `Secure` bật theo `ENV` (production luôn bật, dev chỉ localhost; HTTP non-localhost không được hỗ trợ cho staff).
- nginx: bỏ chèn `X-API-Key` (Plan A đã gỡ `API_KEY`), **ghi đè** `X-Forwarded-For` bằng IP thật, uvicorn chỉ tin nginx; compose không publish cổng API khi chạy cùng frontend (profile dev tách riêng).
- **Dọn trạng thái khi đăng xuất / refresh thất bại (`onLogout`):** huỷ SSE đang chạy, dừng poll thông báo, reset state chat, xoá khoá `shopbot_user_id` cũ, và chính sách giỏ: giỏ khách `shop_cart_guest`; sau đăng nhập gộp vào `shop_cart_<userId>`; khi đăng xuất xoá bộ nhớ trong và không để tài khoản khác thấy giỏ cũ.
- **Hạ tầng test (thêm vào phase này, ~0,5 ngày):** Vitest + jsdom + Testing Library + MSW (fake API/SSE), script `test` trong `package.json`, chạy qua `scripts/check` (chưa dùng CI).
- Giỏ hàng vẫn ở `localStorage` (có thêm khoá theo người dùng ở trên).
- **Phát hành cùng Plan A phase 7 và Plan B phase 2** (API v2 đổi hợp đồng chat; xem `plan.md`).

## Related Code Files

- Create: `frontend/src/auth/{auth-context,require-auth,use-auth}.tsx`, `frontend/src/pages/{login-page,register-page}.tsx`, `frontend/src/lib/http-client.ts`, `frontend/vitest.config.ts`, `frontend/src/test/{setup,msw-handlers}.ts`, `frontend/src/auth/*.test.tsx`
- Modify: `frontend/package.json` (devDependencies + script `test`), `frontend/src/api.ts` (dùng http-client; xoá `user_id` ở dòng 25, 28), `frontend/src/components/{site-layout,chat-widget}.tsx` (bỏ ô mã khách và khoá `shopbot_user_id`, dòng 17-18, 97), `frontend/src/lib/cart.tsx` (khoá giỏ theo người dùng), `frontend/src/App.tsx`, `frontend/nginx.conf.template`, `docker-compose.yml` (bỏ publish cổng API trong profile chạy cùng frontend)

## Implementation Steps

1. Dựng test infra (Vitest/RTL/MSW), script `test`, nối vào `scripts/check`.
2. `http-client.ts` + `AuthProvider` (refresh khi khởi động, single-flight, lỗi 409 có kiểu).
3. Trang đăng nhập/đăng ký (kiểm hợp lệ client + hiển thị lỗi server), quay lại trang trước sau đăng nhập.
4. `RequireAuth`, `RequireRole("staff")`; menu tài khoản trong header; `onLogout` teardown + chính sách giỏ.
5. Chat: chưa đăng nhập hiện lời mời đăng nhập (API 401); đã đăng nhập dùng `user` thật.
6. Cookie `Path`/`proxy_cookie_path`, kiểm Origin cho refresh; nginx XFF; gỡ publish cổng API.
7. Test: khôi phục phiên, 401 → refresh → thử lại, guard theo vai trò, logout dọn sạch (giỏ, chat, poll, SSE), hai tab refresh đồng thời.

## Todo List

- [ ] Test infra frontend (Vitest/RTL/MSW) nối vào `scripts/check`
- [ ] AuthProvider + http-client + single-flight
- [ ] Trang đăng nhập/đăng ký + guard
- [ ] `onLogout` teardown + giỏ theo người dùng + xoá khoá cũ
- [ ] Cookie/nginx/compose (Path, Origin, XFF, port)

## Success Criteria

- [ ] Tải lại trang qua nginx thật vẫn giữ phiên; đăng xuất xoá hẳn phiên và dữ liệu client
- [ ] Khách vào `/staff/*` bị chuyển hướng; không còn nơi nào frontend gửi `user_id`
- [ ] Hai tài khoản dùng chung một trình duyệt không thấy giỏ/chat của nhau

## Risk Assessment

Refresh song song bị coi là tái sử dụng → single-flight + ân hạn server. `Secure` cookie hỏng trên HTTP LAN → chỉ hỗ trợ localhost hoặc HTTPS; cấu hình theo `ENV`.

## Security Considerations

Token truy cập không rời bộ nhớ; refresh chỉ qua cookie HttpOnly + kiểm Origin chống CSRF; XFF chỉ tin nginx; không còn secret nào trong frontend.

## Next Steps

Phase 2 (SSE/thông báo) và phase 5 (console) dùng `AuthProvider` này; test infra dùng cho mọi phase frontend sau.
