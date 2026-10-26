import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { loadEnv } from "vite";

const root = resolve(import.meta.dirname, "..");
const production = loadEnv("production", root, "VITE_");
const client = readFileSync(resolve(root, "src/api/client.ts"), "utf8");
const viteConfig = readFileSync(resolve(root, "vite.config.ts"), "utf8");
if (production.VITE_API_BASE_URL) {
  const url = new URL(production.VITE_API_BASE_URL);
  assert.equal(url.protocol, "https:", "an explicitly configured production API must use HTTPS");
  assert.ok(!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname), "production must not target loopback");
}
const distDir = process.env.CITYRESPONDER_FRONTEND_DIST || resolve(root, "dist");
const index = readFileSync(resolve(distDir, "index.html"), "utf8");
const asset = index.match(/src="\/(assets\/[^" ]+\.js)"/)?.[1];
assert.ok(asset, "production HTML must reference a JavaScript bundle");
assert.ok(readdirSync(resolve(distDir, "assets")).includes(asset.split("/").at(-1)), "referenced bundle must exist");
const bundle = readFileSync(resolve(distDir, asset), "utf8");
assert.ok(!bundle.includes("localhost:8020") && !bundle.includes("127.0.0.1:8020"), "production bundle must not contain a loopback backend URL");
assert.ok(bundle.includes("/api/auth/login") && bundle.includes("/ws/live"), "production bundle must retain API and WebSocket paths");
assert.ok(client.includes("configuredApiBaseUrl || window.location.origin"), "empty API base must use the current page origin");
assert.ok(viteConfig.includes('"/api": { target: "http://127.0.0.1:8020"'), "local API requests must be proxied to the loopback backend");
assert.ok(viteConfig.includes('"/ws/live": { target: "ws://127.0.0.1:8020", ws: true'), "local WebSocket requests must be proxied to the loopback backend");
assert.ok(viteConfig.includes('host: "127.0.0.1"'), "Vite development server must bind to loopback");
console.log("API configuration and production bundle contract PASS");
