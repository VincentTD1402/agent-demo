import { useEffect, useState } from "react";

// Đếm ngược tới 23:59:59 hôm nay (giờ trình duyệt)
function secondsLeft(): number {
  const end = new Date();
  end.setHours(23, 59, 59, 0);
  return Math.max(0, Math.floor((end.getTime() - Date.now()) / 1000));
}

export function FlashSaleTimer() {
  const [s, setS] = useState(secondsLeft);
  useEffect(() => {
    const t = setInterval(() => setS(secondsLeft()), 1000);
    return () => clearInterval(t);
  }, []);
  const parts = [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60];
  return (
    <div className="timer" role="timer" aria-label="Thời gian còn lại của Flash Sale">
      <span className="timer-label">Kết thúc sau</span>
      {parts.map((v, i) => (
        <span key={i} className="timer-cell num">{String(v).padStart(2, "0")}</span>
      ))}
    </div>
  );
}
