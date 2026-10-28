// Client gọi backend qua /api (Vite proxy ở dev, nginx ở production)
export type ChatSource = { source: string; score: number };

/** Sự kiện cuối của luồng /chat/stream */
export type ChatDone = {
  thread_id: string;
  reply: string;
  route: "chat" | "rag" | "out_of_scope";
  sources: ChatSource[];
};

type StreamHandlers = {
  onToken: (text: string) => void;
  onDone: (done: ChatDone) => void;
};

/** Gửi tin nhắn và nhận câu trả lời theo luồng SSE: nhiều `token`, kết thúc bằng `done` (hoặc `error`). */
export async function streamChat(
  message: string,
  threadId: string | undefined,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });
  if (!res.ok || !res.body) {
    const detail = await res.json().then((j) => j.detail).catch(() => null);
    throw new Error(typeof detail === "string" ? detail : `Lỗi ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Mỗi sự kiện SSE kết thúc bằng một dòng trống
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const line = buffer.slice(0, end).trim();
      buffer = buffer.slice(end + 2);
      if (!line.startsWith("data:")) continue;
      const event = JSON.parse(line.slice(5));
      if (event.type === "token") handlers.onToken(event.content);
      else if (event.type === "done") handlers.onDone(event as ChatDone);
      else if (event.type === "error") throw new Error(event.detail ?? "Có lỗi xảy ra");
    }
  }
}

/** Xoá hội thoại phía server; lỗi mạng bỏ qua vì khách đã chuyển sang hội thoại mới. */
export const deleteChat = (threadId: string) =>
  fetch(`/api/chat/${encodeURIComponent(threadId)}`, { method: "DELETE" }).catch(() => undefined);

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
