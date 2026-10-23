import { useState } from "react";
import { CATEGORIES } from "../lib/format";

// Ảnh sản phẩm thật nếu có image_url; lỗi/không có thì vẽ SVG minh hoạ (màu theo slug, icon theo ngành hàng)
function hueOf(slug: string): number {
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

type Props = { slug: string; category: string; imageUrl?: string | null; name?: string; size?: number };

export function ProductImage({ slug, category, imageUrl, name, size = 200 }: Props) {
  const [failed, setFailed] = useState(false);
  if (imageUrl && !failed) {
    return (
      <img
        src={imageUrl}
        alt={name ?? slug}
        width={size}
        height={size}
        loading="lazy"
        style={{ objectFit: "contain", background: "#fff", borderRadius: 16 }}
        onError={() => setFailed(true)}
      />
    );
  }
  const hue = hueOf(slug);
  const icon = CATEGORIES.find((c) => c.slug === category)?.icon ?? "📦";
  const id = `g-${slug}`;
  return (
    <svg viewBox="0 0 200 200" width={size} height={size} role="img" aria-label={name ?? slug}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={`hsl(${hue} 80% 92%)`} />
          <stop offset="1" stopColor={`hsl(${(hue + 40) % 360} 70% 80%)`} />
        </linearGradient>
      </defs>
      <rect width="200" height="200" rx="16" fill={`url(#${id})`} />
      <text x="100" y="118" fontSize="80" textAnchor="middle">
        {icon}
      </text>
    </svg>
  );
}
