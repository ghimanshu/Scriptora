"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, refreshSession } from "@/lib/api-client";
export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(!!path);
  const generation = useRef(0);
  const reload = useCallback(async () => {
    if (!path) return;
    const current = ++generation.current;
    setLoading(true);
    setError(undefined);
    setData(undefined);
    try {
      const value = await api<T>(path);
      if (current === generation.current) setData(value);
    } catch (e) {
      if (current === generation.current) setError(e as Error);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [path, generation]);
  useEffect(() => {
    const counter = generation;
    let active = true;
    queueMicrotask(() => {
      if (active) void reload();
    });
    return () => {
      active = false;
      counter.current++;
    };
  }, [reload]);
  return { data, error, loading, reload, setData };
}
export function ErrorNotice({
  error,
  retry,
}: {
  error?: Error;
  retry?: () => void;
}) {
  const [message, setMessage] = useState("");
  if (!error) return null;
  const expired = error instanceof ApiError && error.status === 401;
  return (
    <div className="notice error" role="alert">
      <div>
        <strong>
          {expired
            ? "Your session needs attention"
            : "We couldn’t complete this request"}
        </strong>
        <p>{error.message}</p>
        {error instanceof ApiError && error.requestId && (
          <small>Request ID: {error.requestId}</small>
        )}
        {message && <p>{message}</p>}
      </div>
      <div className="actions">
        {expired ? (
          <>
            <button
              className="button secondary small"
              onClick={async () => {
                try {
                  await refreshSession();
                  retry?.();
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              Renew session
            </button>
            <a href="/login" className="text-link">
              Sign in
            </a>
          </>
        ) : (
          retry && (
            <button className="button secondary small" onClick={retry}>
              Try again
            </button>
          )
        )}
      </div>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <span className="spinner" /> Loading workspace…
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-mark">↗</span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
