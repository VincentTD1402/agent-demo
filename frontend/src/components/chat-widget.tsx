import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatResponse, PendingAction, resumeThread, sendMessage } from "../api";
import { useChatBridge } from "../lib/chat-context";
import { ApprovalCard } from "./approval-card";
import { ChatMarkdown } from "./chat-markdown";
import { Icon } from "./icons";

type Msg = { role: "user" | "bot"; text: string; at: number };

const SUGGESTIONS = [
  "Tư vấn điện thoại dưới 15 triệu",
  "Kiểm tra đơn hàng A101 của tôi",
  "Tôi muốn hoàn tiền đơn A100",
  "Chính sách hoàn tiền thế nào?",
];

// Chưa có đăng nhập: user_id (UUID) đặt ở trình duyệt; mặc định là khách demo có sẵn đơn mẫu (cố định trong seed)
const DEMO_USER_ID = "11111111-1111-4111-8111-111111111111";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const initialUserId = () => {
  const stored = localStorage.getItem("shopbot_user_id");
  // Giá trị cũ dạng "demo-user" (trước khi user_id là UUID) không còn khớp khách nào: dùng lại mặc định
  return stored && UUID_PATTERN.test(stored) ? stored : DEMO_USER_ID;
};
const clock = (t: number) => new Date(t).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

function Avatar() {
  return <span className="chat-avatar"><Icon name="sparkle" size={16} /></span>;
}

export function ChatWidget() {
  const { open, setOpen, outbox, clearOutbox } = useChatBridge();
  const [userId, setUserId] = useState(initialUserId);
  const [threadId, setThreadId] = useState<string>();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [teaser, setTeaser] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const locked = busy || pending.length > 0 || !userId;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending, busy, open]);

  // Gợi ý nổi sau vài giây nếu khách chưa mở chat
  useEffect(() => {
    if (open) {
      setTeaser(false);
      return;
    }
    const t = setTimeout(() => setTeaser(true), 4000);
    return () => clearTimeout(t);
  }, [open]);

  async function run(call: () => Promise<ChatResponse>) {
    setBusy(true);
    setError(undefined);
    try {
      const res = await call();
      setThreadId(res.thread_id);
      if (res.reply) setMessages((m) => [...m, { role: "bot", text: res.reply as string, at: Date.now() }]);
      setPending(res.status === "awaiting_approval" ? res.pending_actions : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Có lỗi xảy ra");
    } finally {
      setBusy(false);
    }
  }

  function send(text: string) {
    const t = text.trim();
    if (!t || locked) return;
    setMessages((m) => [...m, { role: "user", text: t, at: Date.now() }]);
    void run(() => sendMessage(userId, t, threadId));
  }

  // Trang web nhờ trợ lý (vd nút trên trang sản phẩm): gửi khi widget rảnh
  useEffect(() => {
    if (outbox && !locked) {
      send(outbox);
      clearOutbox();
    }
  }, [outbox]); // eslint-disable-line react-hooks/exhaustive-deps

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
    setInput("");
  }

  function onDecide(approved: boolean) {
    if (!threadId) return;
    const text = approved ? "Tôi đồng ý gửi yêu cầu hoàn tiền" : "Tôi không đồng ý gửi yêu cầu hoàn tiền";
    setMessages((m) => [...m, { role: "user", text, at: Date.now() }]);
    void run(() => resumeThread(threadId, userId, approved));
  }

  function changeUser(id: string) {
    setUserId(id);
    localStorage.setItem("shopbot_user_id", id);
    setThreadId(undefined); // đổi khách = hội thoại mới
    setMessages([]);
    setPending([]);
  }

  return (
    <>
      {!open && (
        <div className="chat-launcher">
          {teaser && (
            <div className="chat-teaser" role="status">
              <button className="teaser-x" onClick={() => setTeaser(false)} aria-label="Ẩn gợi ý"><Icon name="close" size={12} /></button>
              Cần tư vấn chọn máy? Hỏi trợ lý AI nhé!
            </div>
          )}
          <button className="chat-fab" onClick={() => setOpen(true)} aria-label="Mở trợ lý AI">
            <Icon name="sparkle" size={22} />
            <span>Trợ lý AI</span>
            <i className="fab-dot" />
          </button>
        </div>
      )}

      <section className={`chat-panel ${open ? "open" : ""}`} aria-label="Trợ lý AI" aria-hidden={!open}>
        <header>
          <Avatar />
          <div className="grow">
            <b>Trợ lý ShopMobile</b>
            <small><i className="online" /> Trực tuyến · phản hồi trong vài giây</small>
          </div>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Thu nhỏ trợ lý"><Icon name="chevron-down" /></button>
        </header>

        <div className="chat-body" aria-live="polite">
          <div className="msg bot">
            <Avatar />
            <div className="bubble">Xin chào! Mình là trợ lý AI của ShopMobile. Mình có thể tư vấn sản phẩm, tra đơn hàng và hỗ trợ hoàn tiền.</div>
          </div>
          {messages.length === 0 && (
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" disabled={locked} onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "bot" && <Avatar />}
              <div>
                <div className="bubble">{m.role === "bot" ? <ChatMarkdown text={m.text} /> : m.text}</div>
                <time>{clock(m.at)}</time>
              </div>
            </div>
          ))}
          {pending.length > 0 && <ApprovalCard actions={pending} disabled={busy} onDecide={onDecide} />}
          {busy && (
            <div className="msg bot">
              <Avatar />
              <div className="bubble typing" aria-label="Trợ lý đang soạn câu trả lời"><i /><i /><i /></div>
            </div>
          )}
          {error && <div className="error-box">{error}</div>}
          <div ref={bottom} />
        </div>

        <form onSubmit={onSubmit}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={pending.length ? "Hãy xác nhận ở trên" : "Nhập câu hỏi của bạn…"}
            maxLength={4000}
            disabled={locked}
            aria-label="Tin nhắn"
          />
          <button className="send" disabled={locked || !input.trim()} aria-label="Gửi"><Icon name="send" size={18} /></button>
        </form>
        <footer>
          <span>Khách:</span>
          <input value={userId} onChange={(e) => changeUser(e.target.value.trim())} aria-label="Mã khách hàng" />
          <span className="grow" />
          <span>AI có thể nhầm lẫn, hãy kiểm tra thông tin quan trọng.</span>
        </footer>
      </section>
    </>
  );
}
