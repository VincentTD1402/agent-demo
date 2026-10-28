import { useCallback, useEffect, useState } from "react";
import { decideRefund, pendingRefunds, PendingRefund, setOrderStatus } from "../staff-api";
import { vnd } from "../lib/format";

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

/** Tab "Hoàn tiền và đơn hàng": duyệt yêu cầu hoàn tiền, đẩy trạng thái đơn. */
export function StaffRefundsPanel({ staffKey, onMessage }: { staffKey: string; onMessage: (m: string) => void }) {
  const [refunds, setRefunds] = useState<PendingRefund[] | null>(null);
  const [orderCode, setOrderCode] = useState("");

  const load = useCallback(async () => {
    try {
      setRefunds(await pendingRefunds(staffKey));
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }, [staffKey, onMessage]);
  useEffect(() => { void load(); }, [load]);

  async function decide(id: number, approve: boolean, note: string) {
    try {
      const res = await decideRefund(staffKey, id, approve, note);
      onMessage(`Yêu cầu #${id}: ${res.status === "approved" ? "đã duyệt" : "đã từ chối"}`);
      await load();
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }

  async function advance(status: "shipped" | "delivered") {
    try {
      const res = await setOrderStatus(staffKey, orderCode.trim(), status);
      onMessage(`Đơn ${res.code} đã chuyển sang '${res.status}'`);
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }

  return (
    <>
      <section>
        <h2>Yêu cầu hoàn tiền chờ duyệt ({refunds?.length ?? 0})</h2>
        {refunds?.length === 0 && <p className="muted">Không có yêu cầu nào đang chờ.</p>}
        {refunds?.map((r) => <RefundCard key={r.id} refund={r} onDecide={(approve, note) => void decide(r.id, approve, note)} />)}
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
  );
}
