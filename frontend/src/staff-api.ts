// Client API nhân viên: gửi header X-Staff-Key trên mọi lời gọi. Tách riêng khỏi api.ts (API của khách).
import type { Product } from "./api";

export type PendingRefund = {
  id: number;
  order_code: string;
  customer_name: string;
  phone: string;
  payment_method: string;
  payment_status: string;
  order_total_vnd: number;
  reason_code: string;
  details: string;
  item_slugs: string[] | null;
  amount_vnd: number;
  created_at: string;
};

/** Trường chủ shop chỉnh được của một sản phẩm (khớp ProductIn phía backend). */
export type ProductInput = {
  name: string;
  category: string;
  brand: string;
  price_vnd: number;
  old_price_vnd: number | null;
  stock: number;
  rating: number;
  specs: Record<string, string>;
  description: string;
  image_url: string | null;
};

// Lỗi 400 có `detail` là chuỗi tiếng Việt; lỗi kiểm tra đầu vào 422 có `detail` là danh sách {msg}
async function errorMessage(res: Response): Promise<string> {
  const detail = await res.json().then((j) => j.detail).catch(() => null);
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => String(d.msg ?? d).replace(/^Value error, /, "")).join("; ");
  return `Lỗi ${res.status}`;
}

async function call<T>(key: string, path: string, init: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Staff-Key": key };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/staff${path}`, {
    method: init.method ?? "GET",
    headers,
    body: init.form ?? (init.body === undefined ? undefined : JSON.stringify(init.body)),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json() as Promise<T>;
}

export const pendingRefunds = (key: string) => call<PendingRefund[]>(key, "/refunds");
export const decideRefund = (key: string, id: number, approve: boolean, note: string) =>
  call<{ status: string }>(key, `/refunds/${id}/decision`, { method: "POST", body: { approve, note } });
export const setOrderStatus = (key: string, code: string, status: "shipped" | "delivered") =>
  call<{ code: string; status: string }>(key, `/orders/${encodeURIComponent(code)}/status`, { method: "POST", body: { status } });

export const listProducts = (key: string, q = "", category = "") => {
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (category) qs.set("category", category);
  return call<Product[]>(key, `/products?${qs}`);
};
export const createProduct = (key: string, slug: string, input: ProductInput) =>
  call<Product>(key, "/products", { method: "POST", body: { slug, ...input } });
export const updateProduct = (key: string, slug: string, input: ProductInput) =>
  call<Product>(key, `/products/${encodeURIComponent(slug)}`, { method: "PUT", body: input });
export const deleteProduct = (key: string, slug: string) =>
  call<{ deleted: string }>(key, `/products/${encodeURIComponent(slug)}`, { method: "DELETE" });
export const uploadProductImage = (key: string, slug: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return call<Product>(key, `/products/${encodeURIComponent(slug)}/image`, { method: "POST", form });
};
