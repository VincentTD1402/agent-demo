import { FormEvent, useEffect, useRef, useState } from "react";
import { deleteChat, streamChat } from "../api";
import { useChatBridge } from "../lib/chat-context";
import { ChatMarkdown } from "./chat-markdown";
import { Icon } from "./icons";

type Msg = { role: "user" | "bot"; text: string; at: number };

const SUGGESTIONS = [
  "Tư vấn điện thoại dưới 15 triệu",
  "So sánh iPhone 16 và Galaxy S25",
  "Chính sách hoàn tiền thế nào?",
  "Phí vận chuyển tính ra sao?",
];

const clock = (t: number) => new Date(t).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

function Avatar() {
  return <span className="chat-avatar"><Icon name="sparkle" size={16} /></span>;
}

export function ChatWidget() {
  const { open, setOpen, outbox, clearOutbox } = useChatBridge();
  const [threadId, setThreadId] = useState<string>();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [teaser, setTeaser] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy, open]);

  // Ngắt luồng đang nhận khi widget bị gỡ
  useEffect(() => () => abort.current?.abort(), []);

  // Gợi ý nổi sau vài giây nếu khách chưa mở chat
  useEffect(() => {
    if (open) {
      setTeaser(false);
      return;
    }
    const t = setTimeout(() => setTeaser(true), 4000);
    return () => clearTimeout(t);
  }, [open]);

  async function ask(text: string) {
    const controller = new AbortController();
    abort.current = controller;
    setMessages((m) => [...m, { role: "user", text, at: Date.now() }]);
    setBusy(true);
    setError(undefined);
    // Bong bóng trả lời chỉ xuất hiện khi có token đầu tiên; trước đó hiện dấu "đang soạn"
    let started = false;
    const append = (token: string) => {
      if (!started) {
        started = true;
        setMessages((m) => [...m, { role: "bot", text: token, at: Date.now() }]);
      } else {
        setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, text: x.text + token } : x)));
      }
    };
    try {
      await streamChat(
        text,
        threadId,
        {
          onToken: append,
          onDone: (done) => {
            setThreadId(done.thread_id);
            if (!started && done.reply) append(done.reply);
          },
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Có lỗi xảy ra");
    } finally {
      if (abort.current === controller) setBusy(false);
    }
  }

  function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    void ask(t);
  }

  // Trang web nhờ trợ lý (vd nút trên trang sản phẩm): gửi khi widget rảnh
  useEffect(() => {
    if (outbox && !busy) {
      send(outbox);
      clearOutbox();
    }
  }, [outbox]); // eslint-disable-line react-hooks/exhaustive-deps

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
    setInput("");
  }

  function newConversation() {
    abort.current?.abort();
    if (threadId) void deleteChat(threadId);
    setThreadId(undefined);
    setMessages([]);
    setError(undefined);
    setBusy(false);
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
          <button className="icon-btn" onClick={newConversation} disabled={!messages.length && !busy} aria-label="Cuộc trò chuyện mới" title="Cuộc trò chuyện mới"><Icon name="refresh" /></button>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Thu nhỏ trợ lý"><Icon name="chevron-down" /></button>
        </header>

        <div className="chat-body" aria-live="polite">
          <div className="msg bot">
            <Avatar />
            <div className="bubble">Xin chào! Mình là trợ lý AI của ShopMobile. Mình có thể tư vấn sản phẩm, giá, khuyến mãi và giải đáp chính sách giao hàng, bảo hành, đổi trả, hoàn tiền.</div>
          </div>
          {messages.length === 0 && (
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>{s}</button>
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
          {busy && messages[messages.length - 1]?.role !== "bot" && (
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
            placeholder="Nhập câu hỏi của bạn…"
            maxLength={2000}
            disabled={busy}
            aria-label="Tin nhắn"
          />
          <button className="send" disabled={busy || !input.trim()} aria-label="Gửi"><Icon name="send" size={18} /></button>
        </form>
        <footer>
          <span>AI có thể nhầm lẫn, hãy kiểm tra thông tin quan trọng.</span>
        </footer>
      </section>
    </>
  );
}
