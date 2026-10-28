import { useCallback, useEffect, useState } from "react";
import type { Product } from "../api";
import { categoryLabel, CATEGORIES, vnd } from "../lib/format";
import { listProducts } from "../staff-api";
import { StaffProductForm } from "./staff-product-form";

/** Tab "Sản phẩm": danh sách (kể cả hết hàng), tìm kiếm, thêm và sửa. */
export function StaffProductsPanel({ staffKey, onMessage }: { staffKey: string; onMessage: (m: string) => void }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [editing, setEditing] = useState<Product | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      setProducts(await listProducts(staffKey, q.trim(), category));
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "Có lỗi xảy ra");
    }
  }, [staffKey, q, category, onMessage]);
  useEffect(() => { void load(); }, [load]);

  if (editing) {
    return (
      <section>
        <StaffProductForm
          staffKey={staffKey}
          product={editing === "new" ? null : editing}
          onDone={(message) => {
            if (message) onMessage(message);
            setEditing(null);
            void load();
          }}
        />
      </section>
    );
  }

  return (
    <section>
      <h2>Sản phẩm ({products?.length ?? 0})</h2>
      <div className="staff-row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm theo tên, thương hiệu, mô tả" aria-label="Tìm sản phẩm" />
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Danh mục">
          <option value="">Tất cả danh mục</option>
          {CATEGORIES.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
        </select>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>+ Thêm sản phẩm</button>
      </div>
      <div className="product-table" role="table">
        {products?.map((p) => (
          <div className="product-row-admin" role="row" key={p.slug}>
            {p.image_url ? <img className="thumb" src={p.image_url} alt="" loading="lazy" /> : <span className="thumb empty" />}
            <div className="grow"><b>{p.name}</b><small className="muted">{p.slug} · {categoryLabel(p.category)} · {p.brand}</small></div>
            <div className="num price-cell">
              {vnd(p.price_vnd)}
              {p.old_price_vnd && p.old_price_vnd > p.price_vnd && <small className="price-old">{vnd(p.old_price_vnd)}</small>}
            </div>
            <span className={`stock-badge ${p.stock === 0 ? "out" : p.stock <= 5 ? "low" : ""}`}>{p.stock === 0 ? "Hết hàng" : `Còn ${p.stock}`}</span>
            <button className="btn btn-ghost" onClick={() => setEditing(p)}>Sửa</button>
          </div>
        ))}
        {products?.length === 0 && <p className="muted">Không có sản phẩm nào.</p>}
      </div>
    </section>
  );
}
