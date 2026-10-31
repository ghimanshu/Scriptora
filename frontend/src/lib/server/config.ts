import "server-only";
export function config() {
  const production = process.env.NODE_ENV === "production";
  function origin(name: string, fallback: string) {
    const value = process.env[name] || (production ? "" : fallback);
    if (!value) throw new Error(`Missing ${name}`);
    const url = new URL(value);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      url.pathname !== "/"
    )
      throw new Error(`Invalid ${name}`);
    if (production && name !== "BACKEND_API_URL" && url.protocol !== "https:")
      throw new Error(`${name} requires HTTPS`);
    return url.origin;
  }
  const secure = process.env.COOKIE_SECURE === "true";
  if (production && !secure)
    throw new Error("Production requires secure cookies");
  const names = {
    access: process.env.COOKIE_ACCESS_NAME || "publishing_access",
    refresh: process.env.COOKIE_REFRESH_NAME || "publishing_refresh",
    csrf: process.env.CSRF_COOKIE_NAME || "publishing_csrf",
  };
  if (
    new Set(Object.values(names)).size !== 3 ||
    Object.values(names).some(
      (n) =>
        !/^[A-Za-z0-9_-]+$/.test(n) || (production && !n.startsWith("__Host-")),
    )
  )
    throw new Error("Invalid cookie names");
  function positive(name: string, fallback: number) {
    const value = Number(process.env[name] || fallback);
    if (!Number.isSafeInteger(value) || value <= 0)
      throw new Error(`Invalid ${name}`);
    return value;
  }
  return {
    origin: origin("APP_ORIGIN", "http://localhost:3000"),
    internalOrigin: origin("INTERNAL_APP_ORIGIN", "http://127.0.0.1:3000"),
    backend: origin("BACKEND_API_URL", "http://127.0.0.1:8000"),
    secure,
    names,
    timeout: positive("BFF_REQUEST_TIMEOUT_SECONDS", 30) * 1000,
    uploadTimeout: positive("BFF_UPLOAD_TIMEOUT_SECONDS", 120) * 1000,
    maxUpload: positive("BFF_MAX_UPLOAD_BYTES", 20971520),
  };
}
