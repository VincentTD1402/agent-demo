/**
 * Mã phiên của trình duyệt: khoá truy cập giỏ hàng và đơn đã đặt (không phải tài khoản), nên phải là chuỗi ngẫu nhiên khó đoán.
 * Dùng chung cho API giỏ hàng và chat để món trợ lý AI thêm vào giỏ hiện ngay trên giao diện.
 */
const KEY = "shop_session_id";

export function getSessionId(): string {
  let id = localStorage.getItem(KEY);
  if (!id || !/^[A-Za-z0-9_-]{16,64}$/.test(id)) {
    id = crypto.randomUUID().replace(/-/g, "");
    localStorage.setItem(KEY, id);
  }
  return id;
}
