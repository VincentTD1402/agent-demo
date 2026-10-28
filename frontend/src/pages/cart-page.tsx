import { useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/icons";
import { ProductImage } from "../components/product-image";
import { useCart } from "../lib/cart";
import { vnd } from "../lib/format";

const FREE_SHIP_FROM = 500_000;
const SHIP_FEE = 30_000;

export default function CartPage() {
  const { lines, total, setQty, remove } = useCart();
  const [notice, setNotice] = useState(false);

  if (!lines.length) {
    return (
      <div className="empty">
        <Icon name="bag" size={56} />
        <h1>Giỏ hàng đang trống</h1>
        <p className="muted">Hãy chọn vài sản phẩm bạn thích, hoặc nhờ trợ lý AI tư vấn.</p>
        <Link to="/" className="btn btn-primary">Tiếp tục mua sắm</Link>
      </div>
    );
  }

  const ship = total >= FREE_SHIP_FROM ? 0 : SHIP_FEE;
  const remain = Math.max(0, FREE_SHIP_FROM - total);

  return (
    <div className="cart-layout">
      <section>
        <h1>Giỏ hàng <small className="muted">({lines.length} sản phẩm)</small></h1>
        <div className={`ship-bar ${remain === 0 ? "done" : ""}`}>
          <Icon name="truck" size={18} />
          {remain === 0 ? "Đơn hàng được miễn phí vận chuyển" : <>Mua thêm <b className="num">{vnd(remain)}</b> để miễn phí vận chuyển</>}
          <div className="ship-track"><i style={{ width: `${Math.min(100, (total / FREE_SHIP_FROM) * 100)}%` }} /></div>
        </div>
        {lines.map((l) => (
          <div key={l.slug} className="cart-line">
            <ProductImage slug={l.slug} category={l.category} imageUrl={l.image_url} name={l.name} size={88} />
            <div className="grow">
              <Link to={`/san-pham/${l.slug}`} className="cart-name">{l.name}</Link>
              <div className="price num">{vnd(l.price_vnd)}</div>
              <div className="qty">
                <button onClick={() => setQty(l.slug, l.qty - 1)} aria-label="Giảm số lượng"><Icon name="minus" size={14} /></button>
                <span className="num">{l.qty}</span>
                <button onClick={() => setQty(l.slug, l.qty + 1)} aria-label="Tăng số lượng"><Icon name="plus" size={14} /></button>
              </div>
            </div>
            <b className="num line-total">{vnd(l.price_vnd * l.qty)}</b>
            <button className="icon-btn" onClick={() => remove(l.slug)} aria-label={`Xoá ${l.name}`}><Icon name="trash" size={18} /></button>
          </div>
        ))}
      </section>

      <aside className="summary">
        <h2>Tóm tắt đơn hàng</h2>
        <dl>
          <div><dt>Tạm tính</dt><dd className="num">{vnd(total)}</dd></div>
          <div><dt>Vận chuyển</dt><dd className="num">{ship === 0 ? "Miễn phí" : vnd(ship)}</dd></div>
        </dl>
        <div className="summary-total"><span>Tổng cộng</span><b className="price num big">{vnd(total + ship)}</b></div>
        <button className="btn btn-primary" onClick={() => setNotice(true)}>ĐẶT HÀNG</button>
        {notice && (
          <p className="notice">
            Thanh toán chưa được bật trong bản demo. Bạn có thể hỏi trợ lý AI về sản phẩm, giao hàng và chính sách đổi trả.
          </p>
        )}
        <Link to="/" className="link">Tiếp tục mua sắm</Link>
      </aside>
    </div>
  );
}
