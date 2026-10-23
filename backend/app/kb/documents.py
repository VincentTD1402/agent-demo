"""Tài liệu KB mẫu song ngữ (vi/en): hoàn tiền, bảo hành, vận chuyển, trả góp, đổi trả.

Mọi con số chính sách (hạn hoàn, phí ship, ngưỡng miễn phí) sinh từ cấu hình nên KB không bao giờ lệch với
hệ thống. Văn bản là bản mẫu để demo: chủ shop phải xác nhận nội dung trước khi dùng thật.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyNumbers:
    refund_window_days: int
    shipping_fee_vnd: int
    free_shipping_from_vnd: int


def _vnd_vi(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "₫"


def _vnd_en(amount: int) -> str:
    return f"{amount:,} VND"


def _doc(slug: str, lang: str, title: str, category: str, paragraphs: list[str]) -> dict:
    return {"slug": slug, "lang": lang, "title": title, "category": category, "body": "\n\n".join(paragraphs)}


def build_kb_documents(p: PolicyNumbers) -> list[dict]:
    fee_vi, free_vi = _vnd_vi(p.shipping_fee_vnd), _vnd_vi(p.free_shipping_from_vnd)
    fee_en, free_en = _vnd_en(p.shipping_fee_vnd), _vnd_en(p.free_shipping_from_vnd)
    days = p.refund_window_days
    return [
        _doc("refund-policy", "vi", "Chính sách hoàn tiền", "refund", [
            f"Thời hạn: khách có thể yêu cầu hoàn tiền trong {days} ngày kể từ ngày đơn được giao thành công.",
            "Số tiền hoàn tối đa bằng tiền hàng đã thanh toán, không gồm phí vận chuyển (trừ khi lỗi thuộc về cửa hàng) "
            "và trừ số tiền đã chi trả hoàn cho đơn đó trước đó (nếu có).",
            "Chỉ đơn đã giao và đã thanh toán mới đủ điều kiện. Đơn COD chưa thu tiền thì không có khoản nào để hoàn.",
            "Mỗi đơn có tối đa một yêu cầu hoàn tiền đang xử lý. Yêu cầu bị từ chối hoặc huỷ thì có thể gửi lại; "
            "sau khi đã chi trả thì không tạo thêm yêu cầu cho đơn đó.",
            "Nhân viên cửa hàng duyệt từng yêu cầu. Trợ lý tự động chỉ tiếp nhận yêu cầu sau khi khách xác nhận, "
            "không tự quyết định và không hứa hẹn kết quả.",
            "Đơn đã thanh toán nhưng bị huỷ sẽ tự động có yêu cầu hoàn tiền chờ nhân viên xử lý.",
        ]),
        _doc("refund-policy", "en", "Refund policy", "refund", [
            f"Window: customers can request a refund within {days} days of the order being delivered.",
            "The refund is capped at the goods amount actually paid, excluding shipping (unless the shop is at fault) "
            "and minus any amount already paid out as a refund for that order.",
            "Only delivered and paid orders qualify. A cash-on-delivery order that has not been collected has "
            "nothing to refund.",
            "Each order can have at most one active refund request. A rejected or cancelled request can be "
            "resubmitted; once paid out, no further request can be created for that order.",
            "Shop staff review every request. The automated assistant only submits a request after the customer "
            "confirms, and never decides or promises an outcome.",
            "A paid order that gets cancelled automatically gets a refund request waiting for staff.",
        ]),
        _doc("warranty", "vi", "Chính sách bảo hành", "warranty", [
            "Sản phẩm được bảo hành chính hãng theo thời hạn ghi trên phiếu bảo hành hoặc trang sản phẩm của hãng.",
            "Bảo hành áp dụng cho lỗi do nhà sản xuất. Hư hỏng do rơi vỡ, vào nước hoặc tự ý sửa chữa không thuộc "
            "phạm vi bảo hành.",
            "Khi cần bảo hành, khách giữ lại hoá đơn hoặc mã đơn hàng và liên hệ nhân viên để được hướng dẫn "
            "mang máy tới trung tâm bảo hành.",
        ]),
        _doc("warranty", "en", "Warranty policy", "warranty", [
            "Products carry the manufacturer's warranty for the period stated on the warranty card or the "
            "manufacturer's product page.",
            "Warranty covers manufacturing defects. Damage from drops, liquid or unauthorised repairs is not covered.",
            "To claim warranty, keep your invoice or order code and contact staff, who will guide you to a "
            "service centre.",
        ]),
        _doc("shipping", "vi", "Chính sách vận chuyển", "shipping", [
            f"Phí vận chuyển là {fee_vi} cho mỗi đơn. Đơn từ {free_vi} trở lên được miễn phí vận chuyển.",
            "Thời gian giao dự kiến được hiển thị khi đặt hàng và có thể thay đổi theo khu vực và đơn vị vận chuyển.",
            "Sau khi đơn được giao cho đơn vị vận chuyển, khách xem được đơn vị và mã vận đơn ở trang chi tiết đơn.",
            "Địa chỉ giao hàng được chụp lại tại thời điểm đặt và không thể đổi qua trợ lý; cần đổi địa chỉ "
            "thì liên hệ nhân viên trước khi đơn được giao đi.",
        ]),
        _doc("shipping", "en", "Shipping policy", "shipping", [
            f"Shipping costs {fee_en} per order. Orders of {free_en} or more ship free.",
            "The estimated delivery time is shown at checkout and may vary by area and carrier.",
            "Once the order is handed to the carrier, the carrier and tracking code appear on the order page.",
            "The delivery address is captured when the order is placed and cannot be changed through the "
            "assistant; contact staff before the order ships if it must change.",
        ]),
        _doc("installment", "vi", "Mua trả góp", "payment", [
            "Cửa hàng hỗ trợ chuyển đổi trả góp qua thẻ tín dụng của ngân hàng phát hành; điều kiện và lãi suất do "
            "ngân hàng quy định.",
            "Trợ lý không tính lãi hay cam kết duyệt hồ sơ trả góp. Khách cần tư vấn chi tiết sẽ được chuyển cho nhân viên.",
        ]),
        _doc("installment", "en", "Instalment purchases", "payment", [
            "The shop supports converting a purchase to instalments through the issuing bank's credit card; terms "
            "and interest are set by the bank.",
            "The assistant does not calculate interest or promise approval. Customers who need details are "
            "handed over to staff.",
        ]),
        _doc("exchange", "vi", "Đổi trả sản phẩm", "exchange", [
            f"Sản phẩm lỗi do nhà sản xuất có thể được đổi trong {days} ngày kể từ ngày giao, tuỳ tình trạng tồn kho.",
            "Trợ lý không tự thực hiện đổi hàng. Yêu cầu đổi hàng hoặc đổi địa chỉ được chuyển cho nhân viên qua "
            "phiếu hỗ trợ.",
            "Sản phẩm đổi trả cần còn đủ phụ kiện và hộp, không có dấu hiệu hư hỏng do người dùng.",
        ]),
        _doc("exchange", "en", "Exchanges", "exchange", [
            f"A product with a manufacturing defect can be exchanged within {days} days of delivery, subject to stock.",
            "The assistant does not perform exchanges itself. Exchange and address-change requests are passed to "
            "staff through a support ticket.",
            "Returned items must include all accessories and the box, with no user-caused damage.",
        ]),
    ]
