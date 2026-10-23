import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from "react";

type ChatBridge = {
  open: boolean;
  setOpen: (v: boolean) => void;
  /** Tin nhắn trang web muốn gửi thay khách (vd nút "Hỏi trợ lý AI về sản phẩm này") */
  outbox: string | null;
  askAssistant: (text: string) => void;
  clearOutbox: () => void;
};

const Ctx = createContext<ChatBridge | null>(null);

export function ChatBridgeProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [outbox, setOutbox] = useState<string | null>(null);
  const askAssistant = useCallback((text: string) => {
    setOpen(true);
    setOutbox(text);
  }, []);
  const clearOutbox = useCallback(() => setOutbox(null), []);
  const value = useMemo(
    () => ({ open, setOpen, outbox, askAssistant, clearOutbox }),
    [open, outbox, askAssistant, clearOutbox],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChatBridge(): ChatBridge {
  const c = useContext(Ctx);
  if (!c) throw new Error("useChatBridge ngoài ChatBridgeProvider");
  return c;
}
