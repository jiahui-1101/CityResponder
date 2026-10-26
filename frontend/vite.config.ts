import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target: "http://127.0.0.1:8020", changeOrigin: false },
      "/health": { target: "http://127.0.0.1:8020", changeOrigin: false },
      "/ws/live": { target: "ws://127.0.0.1:8020", ws: true, changeOrigin: false },
    },
  },
});
