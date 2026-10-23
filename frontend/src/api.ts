// Client gọi backend qua /api (Vite proxy ở dev, nginx ở production)
export type PendingAction = { tool: string; args: Record<string, unknown> };

export type ChatResponse = {
  thread_id: string;
  status: "completed" | "awaiting_approval";
  reply: string | null;
  pending_actions: PendingAction[];
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail).catch(() => null);
    throw new Error(typeof detail === "string" ? detail : `Lỗi ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const sendMessage = (userId: string, message: string, threadId?: string) =>
  post<ChatResponse>("/v1/chat", { user_id: userId, message, thread_id: threadId });

export const resumeThread = (threadId: string, userId: string, approved: boolean, note?: string) =>
  post<ChatResponse>(`/v1/chat/${threadId}/resume`, { user_id: userId, approved, note });

export type Product = {
  slug: string;
  name: string;
  category: string;
  brand: string;
  price_vnd: number;
  old_price_vnd: number | null;
  rating: number;
  stock: number;
  specs: Record<string, string>;
  description: string;
  image_url: string | null;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) throw new Error(res.status === 404 ? "Không tìm thấy" : `Lỗi ${res.status}`);
  return res.json() as Promise<T>;
}

export const listProducts = (params: { q?: string; category?: string; limit?: number } = {}) => {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.category) qs.set("category", params.category);
  if (params.limit) qs.set("limit", String(params.limit));
  return get<Product[]>(`/v1/products?${qs}`);
};

export const getProduct = (slug: string) => get<Product>(`/v1/products/${encodeURIComponent(slug)}`);
