import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: /api -> backend local (giống nginx ở production)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
