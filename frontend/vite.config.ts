import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const processEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
  const env = { ...loadEnv(mode, ".", ""), ...processEnv };
  return {
  base: mode === "production" ? (env.VITE_BASE_PATH ?? "/") : "/",
  plugins: [react()],
  };
});
