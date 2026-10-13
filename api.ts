import { initializeTelegram } from "./telegram";

const API_URL = import.meta.env.VITE_API_URL ?? "/api/v1";
const initData = initializeTelegram();

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (initData) headers.set("X-Telegram-Init-Data", initData);

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
  }
  return body as T;
}

export function hasTelegramAuth(): boolean {
  return Boolean(initData);
}

