"use client";
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}
function csrf() {
  // Match configured names, including __Host- names, without exposing server config.
  return (
    document.cookie
      .split("; ")
      .map((item) => item.slice(item.indexOf("=") + 1))
      .map(decodeURIComponent)
      .find((value) => /^[a-f0-9]{48}\.[a-f0-9]{64}$/.test(value)) || ""
  );
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (
    !/^\/[a-zA-Z0-9/_?=&%.,:+~-]*$/.test(path) ||
    path.startsWith("//") ||
    path.includes("..")
  )
    throw new Error("Invalid API path");
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrf());
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      data?.error?.code || "REQUEST_FAILED",
      data?.error?.message || "Your request could not be completed.",
      data?.error?.request_id,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function command<T>(
  path: string,
  data: unknown,
  key: string = crypto.randomUUID(),
  method = "POST",
) {
  return api<T>(path, {
    method,
    headers: { "Idempotency-Key": key },
    body: JSON.stringify(data),
  });
}
// Refresh is explicit: failed commands are never automatically replayed.
export async function refreshSession() {
  const refresh = () => api("/auth/refresh", { method: "POST" });
  if (navigator.locks)
    return navigator.locks.request("scriptora-refresh", refresh);
  return refresh();
}
