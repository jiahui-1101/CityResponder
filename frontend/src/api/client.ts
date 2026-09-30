export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010").replace(/\/$/, "");
export const ACCESS_TOKEN_KEY = "cityresponder.access_token";

export function getStoredAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const effectiveToken = token ?? getStoredAccessToken();
  if (effectiveToken) headers.set("Authorization", `Bearer ${effectiveToken}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  const raw = await response.text();
  let body: unknown;
  try { body = raw ? JSON.parse(raw) : null; } catch { body = raw; }
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("cityresponder:unauthorized"));
    const detail = typeof body === "object" && body !== null && "detail" in body ? String(body.detail) : "Request failed";
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export async function apiBinaryRequest(path: string): Promise<Blob> {
  const token = getStoredAccessToken();
  const headers = new Headers({ Accept: "image/*" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { headers });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("cityresponder:unauthorized"));
    throw new ApiError(response.status, response.status === 404 ? "Evidence image not found" : "Unable to load evidence image");
  }
  return response.blob();
}

export type LoginResponse = { access_token: string; token_type: string };
export type CurrentUser = { id: number; email: string; role: "OPERATOR" | "FIREFIGHTER" | "RISK_PLANNER" | "ADMIN"; is_active: boolean; created_at: string };

export function loginRequest(email: string, password: string) {
  return apiRequest<LoginResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function currentUserRequest(token: string) {
  return apiRequest<CurrentUser>("/api/auth/me", {}, token);
}
