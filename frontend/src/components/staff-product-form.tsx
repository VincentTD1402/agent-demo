import { FormEvent, useEffect, useMemo, useState } from "react";
import type { Product } from "../api";
import { CATEGORIES } from "../lib/format";
import { createProduct, deleteProduct, ProductInput, updateProduct, uploadProductImage } from "../staff-api";

type Props = {
  staffKey: string;
  product: Product | null; // null = thêm mới
  onDone: (message?: string) => void; // đóng form; có message thì hiện thông báo
};

const toNumber = (v: string) => (v.trim() === "" ? NaN : Number(v));

/** Form thêm/sửa sản phẩm: mọi giá trị được backend kiểm tra lại; giá, tồn kho đổi ở đây có hiệu lực ngay với website và trợ lý AI. */
export function StaffProductForm({ staffKey, product, onDone }: Props) {
  const [slug, setSlug] = useState(product?.slug ?? "");
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState(product?.category ?? CATEGORIES[0].slug);
  const [brand, setBrand] = useState(product?.brand ?? "");
  const [price, setPrice] = useState(product ? String(product.price_vnd) : "");
  const [oldPrice, setOldPrice] = useState(product?.old_price_vnd ? String(product.old_price_vnd) : "");
  const [stock, setStock] = useState(product ? String(product.stock) : "0");
  const [rating, setRating] = useState(product ? String(product.rating) : "0");
  const [description, setDescription] = useState(product?.description ?? "");
  const [specs, setSpecs] = useState<[string, string][]>(product ? Object.entries(product.specs) : []);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  // Xem trước ảnh vừa chọn; thu hồi URL tạm khi đổi file/đóng form
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : (product?.image_url ?? null)), [file, product]);
  useEffect(() => () => { if (file && preview) URL.revokeObjectURL(preview); }, [file, preview]);

  function setSpec(i: number, part: 0 | 1, value: string) {
    setSpecs((rows) => rows.map((r, j) => (j === i ? (part === 0 ? [value, r[1]] : [r[0], value]) : r)));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const priceVnd = toNumber(price);
    const old = toNumber(oldPrice);
    if (Number.isNaN(priceVnd)) return setError("Nhập giá bán");
    const input: ProductInput = {
      name: name.trim(),
      category,
      brand: brand.trim(),
      price_vnd: priceVnd,
      old_price_vnd: Number.isNaN(old) ? null : old,
      stock: toNumber(stock) || 0,
      rating: toNumber(rating) || 0,
      description: description.trim(),
      specs: Object.fromEntries(specs.filter(([k, v]) => k.trim() && v.trim()).map(([k, v]) => [k.trim(), v.trim()])),
      image_url: product?.image_url ?? null,
    };
    setBusy(true);
    setError(undefined);
    try {
      const saved = product ? await updateProduct(staffKey, product.slug, input) : await createProduct(staffKey, slug.trim(), input);
      if (file) {
        try {
          await uploadProductImage(staffKey, saved.slug, file);
        } catch (err) {
          return onDone(`Đã lưu "${saved.name}" nhưng chưa tải được ảnh: ${err instanceof Error ? err.message : "lỗi"}`);
        }
      }
      onDone(`Đã lưu "${saved.name}"`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    if (!product || !window.confirm(`Xoá "${product.name}"? Thao tác này không hoàn tác được.`)) return;
    setBusy(true);
    try {
      await deleteProduct(staffKey, product.slug);
      onDone(`Đã xoá "${product.name}"`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
      setBusy(false);
    }
  }

  return (
    <form className="product-form" onSubmit={onSubmit}>
      <h2>{product ? `Sửa: ${product.name}` : "Thêm sản phẩm"}</h2>
      <div className="form-grid">
        <label>Mã sản phẩm (slug)
          <input value={slug} onChange={(e) => setSlug(e.target.value)} disabled={!!product} required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="vd: iphone-16-pro" title="Chữ thường, số và dấu gạch ngang; không đổi được sau khi tạo" />
        </label>
        <label>Tên sản phẩm<input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} /></label>
        <label>Danh mục
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
          </select>
        </label>
        <label>Thương hiệu<input value={brand} onChange={(e) => setBrand(e.target.value)} required maxLength={80} /></label>
        <label>Giá bán (₫)<input type="number" min={0} step={1000} value={price} onChange={(e) => setPrice(e.target.value)} required /></label>
        <label>Giá gốc (₫, để trống nếu không giảm giá)<input type="number" min={0} step={1000} value={oldPrice} onChange={(e) => setOldPrice(e.target.value)} /></label>
        <label>Tồn kho<input type="number" min={0} step={1} value={stock} onChange={(e) => setStock(e.target.value)} required /></label>
        <label>Đánh giá (0-5)<input type="number" min={0} max={5} step={0.1} value={rating} onChange={(e) => setRating(e.target.value)} /></label>
      </div>
      <label>Mô tả<textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={5000} /></label>

      <fieldset>
        <legend>Thông số kỹ thuật</legend>
        {specs.map(([k, v], i) => (
          <div className="staff-row" key={i}>
            <input value={k} onChange={(e) => setSpec(i, 0, e.target.value)} placeholder="Tên (vd: Màn hình)" aria-label="Tên thông số" />
            <input value={v} onChange={(e) => setSpec(i, 1, e.target.value)} placeholder="Giá trị (vd: 6.1 inch OLED)" aria-label="Giá trị thông số" />
            <button type="button" className="btn btn-ghost" onClick={() => setSpecs((rows) => rows.filter((_, j) => j !== i))} aria-label="Xoá dòng">Xoá</button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost" onClick={() => setSpecs((rows) => [...rows, ["", ""]])}>+ Thêm thông số</button>
      </fieldset>

      <div className="staff-row image-row">
        {preview ? <img src={preview} alt="Ảnh sản phẩm" className="thumb big" /> : <span className="muted">Chưa có ảnh (website dùng ảnh minh hoạ)</span>}
        <label>Ảnh sản phẩm (PNG, JPG, WEBP, tối đa 2 MB)
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      </div>

      {error && <p className="error-box" role="alert">{error}</p>}
      <div className="staff-row">
        <button className="btn btn-primary" disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => onDone()}>Huỷ</button>
        {product && <button type="button" className="btn btn-ghost danger" disabled={busy} onClick={() => void onDelete()}>Xoá sản phẩm</button>}
      </div>
    </form>
  );
}
