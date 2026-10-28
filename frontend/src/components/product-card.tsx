import { MouseEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Product } from "../api";
import { useCart } from "../lib/cart";
import { demoSold, discountPercent, vnd } from "../lib/format";
import { Icon } from "./icons";
import { ProductImage } from "./product-image";

export function Stars({ rating }: { rating: number }) {
  return (
    <span className="stars" aria-label={`Đánh giá ${rating} trên 5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Icon key={i} name="star" size={13} style={{ opacity: i < Math.round(rating) ? 1 : 0.25 }} />
      ))}
      <small className="num">{rating.toFixed(1)}</small>
    </span>
  );
}

type Props = { p: Product; showSold?: boolean };

export function ProductCard({ p, showSold }: Props) {
  const { add } = useCart();
  const nav = useNavigate();
  const off = discountPercent(p);
  const sold = demoSold(p.slug);
  const soldPct = Math.min(95, Math.round((sold / (sold + p.stock)) * 100));

  const [added, setAdded] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  function buyNow(e: MouseEvent) {
    e.preventDefault();
    // Không mở ngăn kéo vì chuyển thẳng sang trang giỏ hàng; chờ server lưu xong để trang giỏ không hiện trống
    void add(p, 1, false).then(() => nav("/gio-hang"));
  }

  function quickAdd(e: MouseEvent) {
    e.preventDefault(); // không điều hướng sang trang chi tiết
    add(p);
    setAdded(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setAdded(false), 1400);
  }

  return (
    <Link to={`/san-pham/${p.slug}`} className="card">
      <div className="card-media">
        {off > 0 && <span className="pill-off card-off">-{off}%</span>}
        <ProductImage slug={p.slug} category={p.category} imageUrl={p.image_url} name={p.name} size={220} />
      </div>
      <h3 className="card-title">{p.name}</h3>
      <div className="card-price">
        <span className="price num">{vnd(p.price_vnd)}</span>
        {p.old_price_vnd && p.old_price_vnd > p.price_vnd && <span className="price-old">{vnd(p.old_price_vnd)}</span>}
      </div>
      <span className="installment"><Icon name="card" size={13} /> Trả góp 0%</span>
      <Stars rating={p.rating} />
      {showSold && (
        <div className="sold" title={`Đã bán ${sold}`}>
          <div className="sold-bar"><i style={{ width: `${soldPct}%` }} /></div>
          <span>Đã bán {sold}</span>
        </div>
      )}
      {p.stock === 0 ? (
        <div className="oos">Hết hàng</div>
      ) : (
        <div className="card-actions">
          <button className="buy-now" onClick={buyNow}>Mua ngay</button>
          <button
            className={`add-cart ${added ? "added" : ""}`}
            onClick={quickAdd}
            aria-label={`Thêm ${p.name} vào giỏ`}
            title="Thêm vào giỏ"
          >
            <Icon name={added ? "check" : "cart"} size={20} />
          </button>
        </div>
      )}
    </Link>
  );
}
