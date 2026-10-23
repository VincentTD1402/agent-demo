import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listProducts, Product } from "../api";
import { FlashSaleTimer } from "../components/flash-sale-timer";
import { HeroCarousel } from "../components/hero-carousel";
import { Icon } from "../components/icons";
import { ProductCard } from "../components/product-card";
import { ProductRow } from "../components/product-row";
import { CATEGORIES, categoryLabel, discountPercent, vnd } from "../lib/format";
import { useAsync } from "../lib/use-async";
import { useReveal } from "../lib/use-reveal";

const BRANDS = ["Apple", "Samsung", "Xiaomi", "OPPO", "ASUS", "Lenovo", "Dell", "Sony", "Anker"];
const USPS = [
  { icon: "truck", title: "Giao nhanh 2 giờ", sub: "Nội thành, miễn phí từ 500.000₫" },
  { icon: "shield", title: "Chính hãng 100%", sub: "Bảo hành 12 tháng toàn quốc" },
  { icon: "refresh", title: "Đổi trả 7 ngày", sub: "Hoàn tiền nếu không đúng mô tả" },
  { icon: "headset", title: "Trợ lý AI 24/7", sub: "Tư vấn, tra đơn, hỗ trợ hoàn tiền" },
] as const;

// Component riêng để ref reveal gắn ngay khi section được render
function Brands() {
  const ref = useReveal<HTMLElement>();
  return (
    <section className="brands reveal" ref={ref}>
      <h2>Thương hiệu chính hãng</h2>
      <div>
        {BRANDS.map((b) => (
          <Link key={b} to={`/?q=${encodeURIComponent(b)}`}>{b}</Link>
        ))}
      </div>
    </section>
  );
}

function SkeletonGrid({ n = 8 }: { n?: number }) {
  return (
    <div className="grid" aria-busy="true" aria-label="Đang tải sản phẩm">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="card skeleton-card">
          <div className="skeleton" style={{ aspectRatio: "1" }} />
          <div className="skeleton" style={{ height: 16, width: "90%" }} />
          <div className="skeleton" style={{ height: 20, width: "55%" }} />
        </div>
      ))}
    </div>
  );
}

function Grid({ items }: { items: Product[] }) {
  return (
    <div className="grid">
      {items.map((p, i) => (
        <div key={p.slug} className="stagger" style={{ animationDelay: `${Math.min(i, 12) * 40}ms` }}>
          <ProductCard p={p} />
        </div>
      ))}
    </div>
  );
}

function Results({ items, title }: { items: Product[]; title: string }) {
  const [sort, setSort] = useState("default");
  const sorted = useMemo(() => {
    const a = [...items];
    if (sort === "asc") a.sort((x, y) => x.price_vnd - y.price_vnd);
    if (sort === "desc") a.sort((x, y) => y.price_vnd - x.price_vnd);
    if (sort === "off") a.sort((x, y) => discountPercent(y) - discountPercent(x));
    return a;
  }, [items, sort]);
  return (
    <section>
      <div className="results-head">
        <h1>{title} <small className="muted num">({items.length} sản phẩm)</small></h1>
        <label className="sort">
          Sắp xếp
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="default">Nổi bật</option>
            <option value="asc">Giá thấp đến cao</option>
            <option value="desc">Giá cao đến thấp</option>
            <option value="off">Giảm giá nhiều</option>
          </select>
        </label>
      </div>
      {sorted.length ? <Grid items={sorted} /> : <p className="muted">Không có sản phẩm phù hợp. Thử từ khoá khác hoặc hỏi trợ lý AI.</p>}
    </section>
  );
}

export default function HomePage() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? undefined;
  const category = params.get("category") ?? undefined;
  const { data, loading, error } = useAsync(() => listProducts({ q, category }), [q, category]);
  const uspRef = useReveal<HTMLDivElement>();

  if (q || category) {
    if (loading) return <SkeletonGrid />;
    if (error || !data) return <p className="error-box">Không tải được sản phẩm: {error}</p>;
    return <Results items={data} title={q ? `Kết quả cho "${q}"` : categoryLabel(category!)} />;
  }

  const hot = (data ?? []).filter((p) => discountPercent(p) >= 8).sort((a, b) => discountPercent(b) - discountPercent(a));
  const iphone = data?.find((p) => p.slug === "iphone-16-128gb");
  const ipad = data?.find((p) => p.slug === "ipad-gen-10-64gb");

  return (
    <>
      <section className="hero-grid">
        <HeroCarousel />
        <div className="hero-side">
          {[iphone, ipad].map(
            (p, i) =>
              p && (
                <Link key={p.slug} to={`/san-pham/${p.slug}`} className="side-tile" style={{ animationDelay: `${i * 120}ms` }}>
                  <div>
                    <span className="kicker">Giá tốt</span>
                    <b>{p.name}</b>
                    <span className="price num">{vnd(p.price_vnd)}</span>
                  </div>
                  {p.image_url && <img src={p.image_url} alt={p.name} loading="lazy" />}
                </Link>
              ),
          )}
        </div>
      </section>

      <div className="usp reveal" ref={uspRef}>
        {USPS.map((u) => (
          <div key={u.title}>
            <span className="usp-icon"><Icon name={u.icon} size={22} /></span>
            <div><b>{u.title}</b><small>{u.sub}</small></div>
          </div>
        ))}
      </div>

      <nav className="cat-tiles" aria-label="Mua theo danh mục">
        {CATEGORIES.map((c, i) => (
          <Link key={c.slug} to={`/?category=${c.slug}`} className="cat-tile stagger" style={{ animationDelay: `${i * 60}ms` }}>
            <span><Icon name={c.icon} size={28} /></span>
            {c.label}
          </Link>
        ))}
      </nav>

      {loading && <SkeletonGrid n={5} />}
      {error && <p className="error-box">Không tải được sản phẩm: {error}</p>}

      {data && (
        <>
          <div className="flash">
            <ProductRow
              showSold
              items={hot.slice(0, 8)}
              title={<span className="flash-title"><Icon name="bolt" size={26} /> Flash Sale</span>}
              aside={<FlashSaleTimer />}
            />
          </div>
          {CATEGORIES.map((c) => (
            <ProductRow
              key={c.slug}
              title={`${c.label} nổi bật`}
              items={data.filter((p) => p.category === c.slug)}
              moreTo={`/?category=${c.slug}`}
            />
          ))}
          <Brands />
        </>
      )}
    </>
  );
}
