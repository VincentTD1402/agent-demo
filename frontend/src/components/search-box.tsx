import { FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProducts, Product } from "../api";
import { vnd } from "../lib/format";
import { Icon } from "./icons";
import { ProductImage } from "./product-image";

const POPULAR = ["iPhone 16", "MacBook Air", "Laptop gaming", "Tai nghe chống ồn", "Sạc nhanh"];

// Ô tìm kiếm có gợi ý sản phẩm trực tiếp (debounce 250ms) và từ khoá phổ biến
export function SearchBox() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState<Product[]>([]);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    let stale = false;
    const t = setTimeout(() => {
      listProducts({ q: term, limit: 5 })
        .then((r) => !stale && setHits(r))
        .catch(() => !stale && setHits([]));
    }, 250);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [q]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function go(term: string) {
    setOpen(false);
    setQ(term);
    nav(term.trim() ? `/?q=${encodeURIComponent(term.trim())}` : "/");
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    go(q);
  }

  return (
    <div className="search" ref={box}>
      <form onSubmit={onSubmit} role="search">
        <label className="sr-only" htmlFor="site-search">Tìm kiếm sản phẩm</label>
        <input
          id="site-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          placeholder="Bạn muốn tìm gì hôm nay?"
          autoComplete="off"
        />
        <button aria-label="Tìm kiếm">
          <Icon name="search" size={20} />
        </button>
      </form>
      {open && (
        <div className="search-pop">
          {hits.length > 0 ? (
            hits.map((p) => (
              <button key={p.slug} className="hit" onClick={() => { setOpen(false); nav(`/san-pham/${p.slug}`); }}>
                <ProductImage slug={p.slug} category={p.category} imageUrl={p.image_url} name={p.name} size={44} />
                <span className="hit-name">{p.name}</span>
                <span className="price num">{vnd(p.price_vnd)}</span>
              </button>
            ))
          ) : (
            <>
              <div className="pop-title">Tìm kiếm phổ biến</div>
              <div className="pop-chips">
                {POPULAR.map((t) => (
                  <button key={t} onClick={() => go(t)}>{t}</button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
