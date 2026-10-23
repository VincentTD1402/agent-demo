import type { PendingAction } from "../api";
import { vnd } from "../lib/format";
import { Icon } from "./icons";

type Props = {
  actions: PendingAction[];
  disabled: boolean;
  onDecide: (approved: boolean) => void;
};

const LABELS: Record<string, string> = { issue_refund: "Gửi yêu cầu hoàn tiền (nhân viên sẽ duyệt)" };

// Cổng người duyệt: hiện hành động rủi ro cao mà agent đang chờ xác nhận
export function ApprovalCard({ actions, disabled, onDecide }: Props) {
  return (
    <div className="approval" role="alertdialog" aria-label="Cần xác nhận">
      <div className="approval-head"><Icon name="shield" size={18} /> Cần bạn xác nhận</div>
      {actions.map((a, i) => (
        <dl key={i} className="approval-fields">
          <div><dt>Hành động</dt><dd>{LABELS[a.tool] ?? a.tool}</dd></div>
          {a.args.order_id != null && <div><dt>Đơn hàng</dt><dd>{String(a.args.order_id)}</dd></div>}
          {typeof a.args.amount_vnd === "number" && <div><dt>Số tiền</dt><dd className="num">{vnd(a.args.amount_vnd)}</dd></div>}
          {a.args.reason != null && <div><dt>Lý do</dt><dd>{String(a.args.reason)}</dd></div>}
        </dl>
      ))}
      <div className="approval-buttons">
        <button className="btn btn-primary" disabled={disabled} onClick={() => onDecide(true)}>Đồng ý</button>
        <button className="btn btn-ghost" disabled={disabled} onClick={() => onDecide(false)}>Từ chối</button>
      </div>
    </div>
  );
}
