import { MouseEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getProduct, listProducts } from "../api";
import { Icon } from "../components/icons";
import { Stars } from "../components/product-card";
import { ProductImage } from "../components/product-image";
import { ProductRow } from "../components/product-row";
import { useCart } from "../lib/cart";
import { useChatBridge } from "../lib/chat-context";
import { categoryLabel, demoSold, discountPercent, vnd } from "../lib/format";
import { useAsync } from "../lib/use-async";

// Ảnh phóng to theo vị trí con trỏ khi rê chuột
function ZoomImage(props: Parameters<typeof ProductImage>[0]) {
  const [origin, setOrigin] = useState("50% 50%");
  function onMove(e: MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    setOrigin(`${((e.clientX - r.left) / r.width) * 100}% ${((e.clientY - r.top) / r.height) * 100}%`);
  }
  return (
    <div className="zoom" onMouseMove={onMove} style={{ ["--origin" as string]: origin }}>
      <ProductImage {...props} />
    </div>
  );
}

const PERKS = [
  { icon: "truck", text: "Giao nhanh 2 giờ nội thành, miễn phí từ 500.000₫" },
  { icon: "shield", text: "Bảo hành chính hãng 12 tháng, 1 đổi 1 trong 30 ngày nếu lỗi" },
  { icon: "refresh", text: "Hoàn tiền theo chính sách nếu sản phẩm không đúng mô tả" },
] as const;

export default function ProductPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
  const { add } = useCart();
  const { askAssistant } = useChatBridge();
  const [qty, setQty] = useState(1);
  const [tab, setTab] = useState<"desc" | "specs">("specs");
  const { data: p, loading, error } = useAsync(() => getProduct(slug), [slug]);
  const related = useAsync(() => (p ? listProducts({ category: p.category }) : Promise.resolve([])), [p?.category]);

  if (loading) {
    return (
      <div className="detail">
        <div className="skeleton" style={{ aspectRatio: "1" }} />
        <div style={{ display: "grid", gap: 14 }}>
          <div className="skeleton" style={{ height: 32, width: "70%" }} />
          <div className="skeleton" style={{ height: 44, width: "40%" }} />
          <div className="skeleton" style={{ height: 120 }} />
        </div>
      </div>
    );
  }
  if (error || !p) return <p className="error-box">{error ?? "Không tìm thấy sản phẩm"}</p>;
  const off = discountPercent(p);
  const inStock = p.stock > 0;

  return (
    <article>
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Trang chủ</Link> <Icon name="chevron-right" size={14} />
        <Link to={`/?category=${p.category}`}>{categoryLabel(p.category)}</Link> <Icon name="chevron-right" size={14} />
        <span>{p.name}</span>
      </nav>

      <div className="detail">
        <div className="detail-img"><ZoomImage slug={p.slug} category={p.category} imageUrl={p.image_url} name={p.name} size={440} /></div>

        <div className="detail-info">
          <h1>{p.name}</h1>
          <div className="meta">
            <Stars rating={p.rating} />
            <span className="muted">Đã bán {demoSold(p.slug)}</span>
            <span className={inStock ? "instock" : "oos"}>
              {inStock ? <><Icon name="check" size={14} /> Còn hàng ({p.stock})</> : "Tạm hết hàng"}
            </span>
          </div>

          <div className="price-box">
            <span className="price num big-price">{vnd(p.price_vnd)}</span>
            {p.old_price_vnd && p.old_price_vnd > p.price_vnd && <span className="price-old">{vnd(p.old_price_vnd)}</span>}
            {off > 0 && <span className="pill-off">-{off}%</span>}
          </div>

          <ul className="perks">
            {PERKS.map((k) => (
              <li key={k.text}><Icon name={k.icon} size={18} /> {k.text}</li>
            ))}
          </ul>

          <div className="buy-row">
            <div className="qty qty-lg">
              <button onClick={() => setQty((n) => Math.max(1, n - 1))} aria-label="Giảm số lượng"><Icon name="minus" size={16} /></button>
              <span className="num">{qty}</span>
              <button onClick={() => setQty((n) => Math.min(10, n + 1))} aria-label="Tăng số lượng"><Icon name="plus" size={16} /></button>
            </div>
            <button className="btn btn-primary grow-btn" disabled={!inStock} onClick={() => void add(p, qty, false).then(() => nav("/gio-hang"))}>
              MUA NGAY
            </button>
            <button className="btn btn-ghost" disabled={!inStock} onClick={() => add(p, qty)}>
              <Icon name="cart" size={18} /> Thêm vào giỏ
            </button>
          </div>

          <button
            className="ask-ai"
            onClick={() => askAssistant(`Tôi đang xem ${p.name}, tư vấn giúp tôi sản phẩm này có phù hợp không?`)}
          >
            <Icon name="sparkle" size={18} /> Hỏi trợ lý AI về sản phẩm này
          </button>
        </div>
      </div>

      <section className="tabs-card">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "specs"} className={tab === "specs" ? "on" : ""} onClick={() => setTab("specs")}>Thông số kỹ thuật</button>
          <button role="tab" aria-selected={tab === "desc"} className={tab === "desc" ? "on" : ""} onClick={() => setTab("desc")}>Mô tả</button>
        </div>
        {tab === "desc" ? (
          <p className="desc">{p.description}</p>
        ) : (
          <table className="specs">
            <tbody>
              {Object.entries(p.specs).map(([k, v]) => (
                <tr key={k}><th>{k}</th><td>{v}</td></tr>
              ))}
              <tr><th>Thương hiệu</th><td>{p.brand}</td></tr>
            </tbody>
          </table>
        )}
      </section>

      <ProductRow title="Sản phẩm cùng loại" items={(related.data ?? []).filter((x) => x.slug !== p.slug)} />

      <div className="sticky-buy">
        <div><span className="price num">{vnd(p.price_vnd)}</span><small className="muted">{p.name}</small></div>
        <button className="btn btn-primary" disabled={!inStock} onClick={() => add(p, qty)}>Thêm vào giỏ</button>
      </div>
    </article>
  );
}
