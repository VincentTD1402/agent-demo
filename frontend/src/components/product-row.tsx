import { ReactNode, useRef } from "react";
import { Link } from "react-router-dom";
import type { Product } from "../api";
import { useReveal } from "../lib/use-reveal";
import { Icon } from "./icons";
import { ProductCard } from "./product-card";

type Props = { title: ReactNode; items: Product[]; moreTo?: string; showSold?: boolean; aside?: ReactNode };

// Hàng sản phẩm cuộn ngang (scroll-snap) có nút trái/phải trên desktop
function RowInner({ title, items, moreTo, showSold, aside }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const reveal = useReveal<HTMLElement>();
  const scrollBy = (dir: 1 | -1) =>
    scroller.current?.scrollBy({ left: dir * scroller.current.clientWidth * 0.85, behavior: "smooth" });

  return (
    <section className="row reveal" ref={reveal}>
      <header className="row-head">
        <h2>{title}</h2>
        {aside}
        {moreTo && (
          <Link to={moreTo} className="link row-more">
            Xem tất cả <Icon name="chevron-right" size={16} />
          </Link>
        )}
      </header>
      <div className="row-wrap">
        <button className="row-arrow left" onClick={() => scrollBy(-1)} aria-label="Cuộn trái">
          <Icon name="chevron-left" />
        </button>
        <div className="row-scroll" ref={scroller}>
          {items.map((p) => (
            <ProductCard key={p.slug} p={p} showSold={showSold} />
          ))}
        </div>
        <button className="row-arrow right" onClick={() => scrollBy(1)} aria-label="Cuộn phải">
          <Icon name="chevron-right" />
        </button>
      </div>
    </section>
  );
}

export function ProductRow(props: Props) {
  return props.items.length ? <RowInner {...props} /> : null;
}
