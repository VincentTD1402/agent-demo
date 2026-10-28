import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { addCartItem, CartLineData, CartView, fetchCart, Product, removeCartItem, setCartItemQty } from "../api";

export type CartLine = Pick<CartLineData, "slug" | "name" | "category" | "price_vnd" | "image_url" | "qty" | "stock">;

type CartApi = {
  lines: CartLine[];
  count: number;
  total: number;
  /** Thêm vào giỏ (lưu phía server); resolve sau khi server xác nhận nên có thể điều hướng ngay sau `await`. */
  add: (p: Product, qty?: number, openDrawer?: boolean) => Promise<void>;
  drawerOpen: boolean;
  setDrawerOpen: (v: boolean) => void;
  setQty: (slug: string, qty: number) => Promise<void>;
  remove: (slug: string) => Promise<void>;
  /** Tải lại giỏ từ server, dùng khi trợ lý AI vừa thay đổi giỏ. */
  refresh: () => Promise<void>;
  /** Thông báo lỗi ngắn (vd hết hàng) để hiển thị cho khách; tự mất sau vài giây. */
  notice: string | null;
};

const Ctx = createContext<CartApi | null>(null);
const NOTICE_MS = 4000;

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<CartView | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const show = useCallback((message: string) => {
    setNotice(message);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setNotice(null), NOTICE_MS);
  }, []);

  // Chạy một thao tác giỏ hàng: thành công thì lấy giỏ mới từ server, lỗi thì báo cho khách và giữ giỏ cũ
  const run = useCallback(
    async (op: () => Promise<CartView>) => {
      try {
        setCart(await op());
      } catch (e) {
        show(e instanceof Error ? e.message : "Không cập nhật được giỏ hàng");
      }
    },
    [show],
  );

  const refresh = useCallback(async () => {
    try {
      setCart(await fetchCart());
    } catch {
      /* giữ giỏ đang hiển thị; lần thao tác sau sẽ tải lại */
    }
  }, []);

  useEffect(() => {
    localStorage.removeItem("shop_cart"); // giỏ cũ lưu cục bộ trước khi có giỏ phía server
    void refresh();
  }, [refresh]);

  const api = useMemo<CartApi>(() => {
    const lines = cart?.lines ?? [];
    return {
      lines,
      count: lines.reduce((n, l) => n + l.qty, 0),
      total: cart?.subtotal_vnd ?? 0,
      drawerOpen,
      setDrawerOpen,
      notice,
      refresh,
      add: async (p, qty = 1, openDrawer = true) => {
        await run(() => addCartItem(p.slug, qty));
        if (openDrawer) setDrawerOpen(true);
      },
      setQty: (slug, qty) => run(() => setCartItemQty(slug, Math.max(1, Math.min(10, qty)))),
      remove: (slug) => run(() => removeCartItem(slug)),
    };
  }, [cart, drawerOpen, notice, refresh, run]);
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useCart(): CartApi {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCart ngoài CartProvider");
  return c;
}
