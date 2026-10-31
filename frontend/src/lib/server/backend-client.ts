import "server-only";
import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { config } from "./config";
import { mutationAllowed } from "./csrf";
import { allowed, publicPath } from "./route-allowlist";

export function failure(
  status: number,
  code: string,
  message: string,
  requestId: string = randomUUID(),
) {
  return NextResponse.json(
    { error: { code, message, request_id: requestId } },
    {
      status,
      headers: { "Cache-Control": "no-store", "X-Request-ID": requestId },
    },
  );
}
export async function backend(path: string, init: RequestInit) {
  const c = config();
  return fetch(`${c.backend}/api/v1/${path}`, {
    ...init,
    redirect: "manual",
    cache: "no-store",
  });
}
export async function safeResponse(upstream: Response, requestId: string) {
  const headers = new Headers({
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Request-ID": upstream.headers.get("x-request-id") || requestId,
  });
  for (const key of [
    "content-type",
    "content-disposition",
    "etag",
    "retry-after",
  ]) {
    const value = upstream.headers.get(key);
    if (value) headers.set(key, value);
  }
  if (upstream.status >= 300 && upstream.status < 400)
    return failure(
      502,
      "UPSTREAM_REDIRECT",
      "The service returned an unexpected redirect.",
      requestId,
    );
  if (!upstream.ok) {
    const data = await upstream.json().catch(() => null);
    const upstreamCode = data?.error?.code ?? data?.detail?.code;
    const code =
      typeof upstreamCode === "string" && /^[A-Z][A-Z0-9_]{1,80}$/.test(upstreamCode)
        ? upstreamCode : "REQUEST_FAILED";
    const messages: Record<number, string> = {
      400: "The request is incomplete. Reload the page and try again.",
      401: "Sign in to continue.",
      403: "You do not have permission for this action.",
      404: "This resource is unavailable.",
      409: "This item changed or its deadline passed. Refresh before trying again.",
      412: "A newer version exists. Refresh before saving.",
      413: "The file exceeds the upload limit.",
      415: "This file type is unsupported.",
      422: "Please check the required fields and file status.",
      429: "Too many requests. Please try again later.",
    };
    return failure(
      upstream.status,
      code,
      messages[upstream.status] ||
        "The service could not complete your request.",
      headers.get("x-request-id")!,
    );
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers });
}
export async function forward(request: NextRequest, path: string) {
  if (!allowed(request.method, path))
    return failure(404, "NOT_FOUND", "This endpoint is unavailable.");
  const c = config();
  const isPublic = publicPath(path);
  if (
    !["GET", "HEAD"].includes(request.method) &&
    !mutationAllowed(request, !isPublic)
  )
    return failure(
      403,
      "CSRF_FAILED",
      "Security validation failed. Reload the page.",
    );
  const access = request.cookies.get(c.names.access)?.value;
  if (!isPublic && !access)
    return failure(401, "AUTH_REQUIRED", "Sign in to continue.");
  const requestId = randomUUID();
  const headers = new Headers({ "X-Request-ID": requestId });
  if (access && !isPublic) headers.set("Authorization", `Bearer ${access}`);
  for (const key of ["content-type", "if-match", "idempotency-key", "accept"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    path === "files" ? c.uploadTimeout : c.timeout,
  );
  let size = 0;
  const limit = path === "files" ? c.maxUpload + 65536 : 1048576;
  if (Number(request.headers.get("content-length") || 0) > limit) {
    clearTimeout(timeout);
    return failure(
      413,
      "BODY_TOO_LARGE",
      "The request exceeds the size limit.",
    );
  }
  const body = request.body?.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, output) {
        size += chunk.byteLength;
        if (size > limit) {
          controller.abort();
          throw new Error("BODY_TOO_LARGE");
        }
        output.enqueue(chunk);
      },
    }),
  );
  try {
    const init: RequestInit & { duplex?: string } = {
      method: request.method,
      headers,
      signal: controller.signal,
    };
    if (body && request.method !== "GET") {
      init.body = body;
      init.duplex = "half";
    }
    const upstream = await backend(path + request.nextUrl.search, init);
    // Download bodies remain streamed. The timeout also covers upstream body consumption.
    const response = await safeResponse(upstream, requestId);
    if (!response.body) {
      clearTimeout(timeout);
      return response;
    }
    let downloaded = 0;
    const streamed = response.body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, output) {
          downloaded += chunk.byteLength;
          if (downloaded > c.maxUpload + 65536) {
            controller.abort();
            clearTimeout(timeout);
            throw new Error("RESPONSE_TOO_LARGE");
          }
          output.enqueue(chunk);
        },
        flush() {
          clearTimeout(timeout);
        },
      }),
    );
    return new NextResponse(streamed, {
      status: response.status,
      headers: response.headers,
    });
  } catch {
    clearTimeout(timeout);
    return failure(
      size > limit ? 413 : 502,
      size > limit ? "BODY_TOO_LARGE" : "BACKEND_UNAVAILABLE",
      size > limit
        ? "The request exceeds the size limit."
        : "The publishing service is unavailable. Please try again shortly.",
      requestId,
    );
  }
}
