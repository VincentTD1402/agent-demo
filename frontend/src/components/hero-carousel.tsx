import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "./icons";

type Slide = {
  kicker: string;
  title: string;
  sub: string;
  cta: string;
  to: string;
  tone: string; // màu nền
  images: { src: string; alt: string }[];
};

// Nội dung khuyến mãi khớp giá trong dữ liệu mẫu (S25 giảm 2tr, MacBook Air giảm 3tr)
const SLIDES: Slide[] = [
  {
    kicker: "Flagship 2025",
    title: "Galaxy S25, AI trong tầm tay",
    sub: "Giảm đến 2 triệu, trả góp 0%",
    cta: "Mua ngay",
    to: "/san-pham/samsung-galaxy-s25-256gb",
    tone: "#e6ecf7",
    images: [{ src: "/products/samsung-galaxy-s25-256gb.jpg", alt: "Samsung Galaxy S25" }],
  },
  {
    kicker: "Mỏng nhẹ, pin cả ngày",
    title: "MacBook Air M3 giảm 3 triệu",
    sub: "Chip M3 mạnh mẽ, không quạt, êm tuyệt đối",
    cta: "Xem chi tiết",
    to: "/san-pham/macbook-air-m3-13",
    tone: "#dcebf7",
    images: [{ src: "/products/macbook-air-m3-13.png", alt: "MacBook Air M3" }],
  },
  {
    kicker: "Phụ kiện chính hãng",
    title: "Nghe nhạc, sạc nhanh, đi đâu cũng tiện",
    sub: "Tai nghe, sạc, pin dự phòng từ 290.000₫",
    cta: "Khám phá phụ kiện",
    to: "/?category=phu-kien",
    tone: "#f3e9d2",
    images: [
      { src: "/products/airpods-pro-2-usb-c.jpg", alt: "AirPods Pro 2" },
      { src: "/products/sony-wh-1000xm5.png", alt: "Sony WH-1000XM5" },
      { src: "/products/anker-sac-20w.png", alt: "Sạc Anker 20W" },
    ],
  },
];
const INTERVAL = 5500;

export function HeroCarousel() {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const t = setTimeout(() => setI((n) => (n + 1) % SLIDES.length), INTERVAL);
    return () => clearTimeout(t);
  }, [i, paused]);

  const go = (n: number) => setI((n + SLIDES.length) % SLIDES.length);

  return (
    <div
      className="hero"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-roledescription="carousel"
      aria-label="Khuyến mãi nổi bật"
    >
      {SLIDES.map((s, n) => (
        <article key={s.title} className={`slide ${n === i ? "on" : ""}`} style={{ background: s.tone }} aria-hidden={n !== i}>
          <div className="slide-copy">
            <span className="kicker">{s.kicker}</span>
            <h2>{s.title}</h2>
            <p>{s.sub}</p>
            <Link to={s.to} className="btn btn-dark" tabIndex={n === i ? 0 : -1}>
              {s.cta} <Icon name="chevron-right" size={18} />
            </Link>
          </div>
          <div className={`slide-art art-${s.images.length}`}>
            {s.images.map((im) => (
              <img key={im.src} src={im.src} alt={im.alt} loading={n === 0 ? "eager" : "lazy"} />
            ))}
          </div>
        </article>
      ))}
      <button className="hero-arrow left" onClick={() => go(i - 1)} aria-label="Slide trước"><Icon name="chevron-left" /></button>
      <button className="hero-arrow right" onClick={() => go(i + 1)} aria-label="Slide sau"><Icon name="chevron-right" /></button>
      <div className="hero-dots">
        {SLIDES.map((s, n) => (
          <button key={s.title} className={n === i ? "on" : ""} onClick={() => go(n)} aria-label={`Slide ${n + 1}`}>
            {n === i && !paused && <i key={i} style={{ animationDuration: `${INTERVAL}ms` }} />}
          </button>
        ))}
      </div>
    </div>
  );
}
