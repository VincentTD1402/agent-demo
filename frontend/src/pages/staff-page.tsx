import { FormEvent, useCallback, useState } from "react";
import { PendingRefund, staffDecideRefund, staffPendingRefunds, staffSetOrderStatus } from "../api";
import { vnd } from "../lib/format";

const KEY_STORAGE = "shop_staff_key"; // sessionStorage: mất khi đóng tab, không để khoá nhân viên lại lâu trên máy
const REASONS: Record<string, string> = {
  not_as_described: "Không đúng mô tả",
  defective: "Sản phẩm lỗi",
  wrong_or_missing_item: "Giao sai/thiếu hàng",
  damaged_in_shipping: "Hư hỏng khi vận chuyển",
};

function RefundCard({ refund, onDecide }: { refund: PendingRefund; onDecide: (approve: boolean, note: string) => void }) {
  const [note, setNote] = useState("");
  return (
    <div className="refund-card">
      <dl>
        <dt>Yêu cầu</dt><dd>#{refund.id} · đơn {refund.order_code}</dd>
        <dt>Khách</dt><dd>{refund.customer_name} · {refund.phone}</dd>
        <dt>Thanh toán</dt><dd>{refund.payment_method === "cod" ? "COD" : "Trực tuyến"} ({refund.payment_status}) · tổng đơn {vnd(refund.order_total_vnd)}</dd>
        <dt>Lý do</dt><dd>{REASONS[refund.reason_code] ?? refund.reason_code}{refund.details ? `: ${refund.details}` : ""}</dd>
        {refund.item_slugs && <><dt>Sản phẩm</dt><dd>{refund.item_slugs.join(", ")}</dd></>}
        <dt>Số tiền hoàn</dt><dd><b className="price num">{vnd(refund.amount_vnd)}</b></dd>
      </dl>
      <div className="staff-row">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ghi chú (tuỳ chọn)" maxLength={500} aria-label="Ghi chú" />
        <button className="btn btn-primary" onClick={() => onDecide(true, note)}>Duyệt hoàn tiền</button>
        <button className="btn btn-ghost" onClick={() => onDecide(false, note)}>Từ chối</button>
      </div>
    </div>
  );
}

export default function StaffPage() {
  const [key, setKey] = useState(() => sessionStorage.getItem(KEY_STORAGE) ?? "");
  const [refunds, setRefunds] = useState<PendingRefund[] | null>(null);
  const [message, setMessage] = useState<string>();
  const [orderCode, setOrderCode] = useState("");

  const load = useCallback(async (k: string) => {
    try {
      setRefunds(await staffPendingRefunds(k));
      sessionStorage.setItem(KEY_STORAGE, k);
      setMessage(undefined);
    } catch (e) {
      setRefunds(null);
      setMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }, []);

  function onLogin(e: FormEvent) {
    e.preventDefault();
    void load(key.trim());
  }

  async function decide(id: number, approve: boolean, note: string) {
    try {
      const res = await staffDecideRefund(key, id, approve, note);
      setMessage(`Yêu cầu #${id}: ${res.status === "approved" ? "đã duyệt" : "đã từ chối"}`);
      await load(key);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }

  async function advance(status: "shipped" | "delivered") {
    try {
      const res = await staffSetOrderStatus(key, orderCode.trim(), status);
      setMessage(`Đơn ${res.code} đã chuyển sang '${res.status}'`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }

  return (
    <div className="staff">
      <h1>Khu vực nhân viên</h1>
      <section>
        <h2>Đăng nhập</h2>
        <form className="staff-row" onSubmit={onLogin}>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Khoá nhân viên (X-Staff-Key)" aria-label="Khoá nhân viên" />
          <button className="btn btn-primary" disabled={!key.trim()}>Xem yêu cầu hoàn tiền</button>
        </form>
        {message && <p className="notice">{message}</p>}
      </section>

      {refunds && (
        <>
          <section>
            <h2>Yêu cầu hoàn tiền chờ duyệt ({refunds.length})</h2>
            {refunds.length === 0 && <p className="muted">Không có yêu cầu nào đang chờ.</p>}
            {refunds.map((r) => (
              <RefundCard key={r.id} refund={r} onDecide={(approve, note) => void decide(r.id, approve, note)} />
            ))}
          </section>
          <section>
            <h2>Cập nhật trạng thái đơn</h2>
            <div className="staff-row">
              <input value={orderCode} onChange={(e) => setOrderCode(e.target.value)} placeholder="Mã đơn, vd SM001000" aria-label="Mã đơn" />
              <button className="btn btn-ghost" disabled={!orderCode.trim()} onClick={() => void advance("shipped")}>Đang giao</button>
              <button className="btn btn-ghost" disabled={!orderCode.trim()} onClick={() => void advance("delivered")}>Đã giao</button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
