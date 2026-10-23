import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useCart } from "../lib/cart";
import { vnd } from "../lib/format";
import { Icon } from "./icons";
import { ProductImage } from "./product-image";

// Ngăn kéo giỏ hàng trượt từ phải, mở khi thêm sản phẩm
export function CartDrawer() {
  const { lines, total, drawerOpen, setDrawerOpen, setQty, remove } = useCart();

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen, setDrawerOpen]);

  return (
    <div className={`drawer-root ${drawerOpen ? "open" : ""}`} aria-hidden={!drawerOpen}>
      <div className="drawer-scrim" onClick={() => setDrawerOpen(false)} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Giỏ hàng">
        <header>
          <h2>Giỏ hàng</h2>
          <button className="icon-btn" onClick={() => setDrawerOpen(false)} aria-label="Đóng giỏ hàng">
            <Icon name="close" />
          </button>
        </header>
        <div className="drawer-body">
          {lines.length === 0 && <p className="muted">Chưa có sản phẩm nào.</p>}
          {lines.map((l) => (
            <div key={l.slug} className="drawer-line">
              <ProductImage slug={l.slug} category={l.category} imageUrl={l.image_url} name={l.name} size={64} />
              <div className="grow">
                <Link to={`/san-pham/${l.slug}`} onClick={() => setDrawerOpen(false)}>{l.name}</Link>
                <div className="price num">{vnd(l.price_vnd)}</div>
                <div className="qty">
                  <button onClick={() => setQty(l.slug, l.qty - 1)} aria-label="Giảm số lượng"><Icon name="minus" size={14} /></button>
                  <span className="num">{l.qty}</span>
                  <button onClick={() => setQty(l.slug, l.qty + 1)} aria-label="Tăng số lượng"><Icon name="plus" size={14} /></button>
                </div>
              </div>
              <button className="icon-btn" onClick={() => remove(l.slug)} aria-label={`Xoá ${l.name}`}>
                <Icon name="trash" size={18} />
              </button>
            </div>
          ))}
        </div>
        <footer>
          <div className="drawer-total"><span>Tạm tính</span><b className="price num big">{vnd(total)}</b></div>
          <Link to="/gio-hang" className="btn btn-primary" onClick={() => setDrawerOpen(false)}>Xem giỏ hàng &amp; đặt hàng</Link>
        </footer>
      </aside>
    </div>
  );
}
