import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import type { Product } from "../api";

export type CartLine = Pick<Product, "slug" | "name" | "category" | "price_vnd" | "image_url"> & { qty: number };

type CartApi = {
  lines: CartLine[];
  count: number;
  total: number;
  add: (p: Product, qty?: number, openDrawer?: boolean) => void;
  drawerOpen: boolean;
  setDrawerOpen: (v: boolean) => void;
  setQty: (slug: string, qty: number) => void;
  remove: (slug: string) => void;
};

const Ctx = createContext<CartApi | null>(null);
const KEY = "shop_cart";

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(KEY) ?? "[]");
    } catch {
      return [];
    }
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(lines));
  }, [lines]);

  const api = useMemo<CartApi>(
    () => ({
      lines,
      count: lines.reduce((n, l) => n + l.qty, 0),
      total: lines.reduce((n, l) => n + l.qty * l.price_vnd, 0),
      drawerOpen,
      setDrawerOpen,
      add: (p, qty = 1, openDrawer = true) => {
        setLines((ls) =>
          ls.some((l) => l.slug === p.slug)
            ? ls.map((l) => (l.slug === p.slug ? { ...l, qty: Math.min(10, l.qty + qty) } : l))
            : [...ls, { slug: p.slug, name: p.name, category: p.category, price_vnd: p.price_vnd, image_url: p.image_url, qty }],
        );
        if (openDrawer) setDrawerOpen(true);
      },
      setQty: (slug, qty) =>
        setLines((ls) => ls.map((l) => (l.slug === slug ? { ...l, qty: Math.max(1, Math.min(10, qty)) } : l))),
      remove: (slug) => setLines((ls) => ls.filter((l) => l.slug !== slug)),
    }),
    [lines, drawerOpen],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useCart(): CartApi {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCart ngoài CartProvider");
  return c;
}
