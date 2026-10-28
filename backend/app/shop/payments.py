"""Cổng thanh toán. Hiện chỉ có bản giả lập (luôn thành công); thay bằng cổng thật bằng cách cài đặt `PaymentGateway`."""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PaymentResult:
    ok: bool
    reference: str  # mã giao dịch của cổng, lưu vào orders.payment_ref
    message: str = ""


class PaymentGateway(Protocol):
    def charge(self, order_code: str, amount_vnd: int) -> PaymentResult: ...


class SimulatedPaymentGateway:
    """Không trừ tiền thật: dùng cho demo/test. Mã giao dịch có tiền tố SIM- để dễ phân biệt."""

    def charge(self, order_code: str, amount_vnd: int) -> PaymentResult:
        return PaymentResult(ok=True, reference=f"SIM-{uuid.uuid4().hex[:12].upper()}")
