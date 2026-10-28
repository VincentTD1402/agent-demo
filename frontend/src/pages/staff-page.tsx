import { FormEvent, useCallback, useState } from "react";
import { StaffProductsPanel } from "../components/staff-products-panel";
import { StaffRefundsPanel } from "../components/staff-refunds-panel";
import { pendingRefunds } from "../staff-api";

const KEY_STORAGE = "shop_staff_key"; // sessionStorage: mất khi đóng tab, không để khoá nhân viên lại lâu trên máy

type Tab = "refunds" | "products";

export default function StaffPage() {
  const [key, setKey] = useState(() => sessionStorage.getItem(KEY_STORAGE) ?? "");
  const [authorized, setAuthorized] = useState<string | null>(null); // khoá đã được server chấp nhận
  const [tab, setTab] = useState<Tab>("products");
  const [message, setMessage] = useState<string>();

  const showMessage = useCallback((m: string) => setMessage(m), []);

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    const candidate = key.trim();
    try {
      await pendingRefunds(candidate); // gọi thử một endpoint nhân viên để kiểm tra khoá
      sessionStorage.setItem(KEY_STORAGE, candidate);
      setAuthorized(candidate);
      setMessage(undefined);
    } catch (err) {
      setAuthorized(null);
      setMessage(err instanceof Error ? err.message : "Có lỗi xảy ra");
    }
  }

  return (
    <div className="staff">
      <h1>Khu vực nhân viên</h1>
      <section>
        <h2>Đăng nhập</h2>
        <form className="staff-row" onSubmit={onLogin}>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Khoá nhân viên (X-Staff-Key)" aria-label="Khoá nhân viên" />
          <button className="btn btn-primary" disabled={!key.trim()}>{authorized ? "Đăng nhập lại" : "Đăng nhập"}</button>
        </form>
        {message && <p className="notice" role="status">{message}</p>}
      </section>

      {authorized && (
        <>
          <div className="staff-tabs" role="tablist">
            <button role="tab" aria-selected={tab === "products"} onClick={() => setTab("products")}>Sản phẩm</button>
            <button role="tab" aria-selected={tab === "refunds"} onClick={() => setTab("refunds")}>Hoàn tiền và đơn hàng</button>
          </div>
          {tab === "products" ? (
            <StaffProductsPanel staffKey={authorized} onMessage={showMessage} />
          ) : (
            <StaffRefundsPanel staffKey={authorized} onMessage={showMessage} />
          )}
        </>
      )}
    </div>
  );
}
