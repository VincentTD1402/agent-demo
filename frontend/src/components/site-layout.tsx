import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { useCart } from "../lib/cart";
import { CATEGORIES } from "../lib/format";
import { CartDrawer } from "./cart-drawer";
import { ChatWidget } from "./chat-widget";
import { Icon } from "./icons";
import { SearchBox } from "./search-box";

const PROMOS = [
  "Miễn phí giao nhanh 2 giờ nội thành cho đơn từ 500.000₫",
  "Trả góp 0% qua thẻ tín dụng, duyệt trong 5 phút",
  "Đổi mới 30 ngày nếu lỗi do nhà sản xuất",
];

function PromoStrip() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % PROMOS.length), 4000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="promo-strip" aria-live="off">
      <div className="container promo-track">
        <span key={i}>{PROMOS[i]}</span>
      </div>
    </div>
  );
}

function Header() {
  const { count, setDrawerOpen } = useCart();
  const [params] = useSearchParams();
  const active = params.get("category");
  return (
    <header className="site-header">
      <PromoStrip />
      <div className="container topbar">
        <Link to="/" className="logo" aria-label="ShopMobile - trang chủ">
          Shop<span>Mobile</span>
        </Link>
        <SearchBox />
        <button className="cart-btn" onClick={() => setDrawerOpen(true)} aria-label={`Giỏ hàng, ${count} sản phẩm`}>
          <Icon name="cart" size={22} />
          <span className="cart-label">Giỏ hàng</span>
          {count > 0 && <b key={count} className="cart-count num">{count}</b>}
        </button>
      </div>
      <nav className="container catnav" aria-label="Danh mục sản phẩm">
        {CATEGORIES.map((c) => (
          <Link
            key={c.slug}
            to={`/?category=${c.slug}`}
            className={active === c.slug ? "active" : ""}
            aria-current={active === c.slug ? "page" : undefined}
          >
            <Icon name={c.icon} size={18} /> {c.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div>
          <div className="logo logo-light">Shop<span>Mobile</span></div>
          <p>Điện thoại, laptop và phụ kiện chính hãng. Trợ lý AI tư vấn sản phẩm và giải đáp chính sách 24/7.</p>
        </div>
        <div>
          <b>Mua hàng</b>
          <Link to="/?category=dien-thoai">Điện thoại</Link>
          <Link to="/?category=laptop">Laptop</Link>
          <Link to="/?category=phu-kien">Phụ kiện</Link>
        </div>
        <div>
          <b>Chính sách</b>
          <span>Bảo hành chính hãng 12 tháng</span>
          <span>Đổi trả trong 7 ngày</span>
          <span>Hoàn tiền theo quy định</span>
        </div>
        <div>
          <b>Hỗ trợ</b>
          <span>Tổng đài 1800 0000</span>
          <span>7:30 - 22:00 hằng ngày</span>
        </div>
      </div>
      <div className="container footer-note">
        © ShopMobile — website demo, dữ liệu sản phẩm mang tính minh hoạ. Ảnh sản phẩm từ Wikimedia Commons, trang chính
        hãng và nhà bán lẻ, <a href="/products/CREDITS.txt">xem nguồn ảnh</a>.
      </div>
    </footer>
  );
}

// Cuộn lên đầu khi đổi trang
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [pathname]);
  return null;
}

export function SiteLayout() {
  const { pathname, search } = useLocation();
  return (
    <>
      <ScrollToTop />
      <Header />
      <main className="container main" key={pathname + search}>
        <div className="page">
          <Outlet />
        </div>
      </main>
      <Footer />
      <CartDrawer />
      <ChatWidget />
    </>
  );
}
