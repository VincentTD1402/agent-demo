import type { Product } from "../api";

export const vnd = (n: number) => `${n.toLocaleString("vi-VN")}₫`;

export function discountPercent(p: Pick<Product, "price_vnd" | "old_price_vnd">): number {
  return p.old_price_vnd && p.old_price_vnd > p.price_vnd
    ? Math.round((1 - p.price_vnd / p.old_price_vnd) * 100)
    : 0;
}

export const CATEGORIES = [
  { slug: "dien-thoai", label: "Điện thoại", icon: "phone" },
  { slug: "laptop", label: "Laptop", icon: "laptop" },
  { slug: "may-tinh-bang", label: "Tablet", icon: "tablet" },
  { slug: "dong-ho", label: "Đồng hồ", icon: "watch" },
  { slug: "phu-kien", label: "Phụ kiện", icon: "headset" },
] as const;

export const categoryLabel = (slug: string) => CATEGORIES.find((c) => c.slug === slug)?.label ?? slug;

/** Số "đã bán" minh hoạ, cố định theo slug (chưa có dữ liệu bán hàng thật). */
export function demoSold(slug: string): number {
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) % 1000;
  return 40 + (h % 160);
}
