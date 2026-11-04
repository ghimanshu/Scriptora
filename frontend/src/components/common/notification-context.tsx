"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api-client";
import type { NotificationSummary } from "@/types/api";

const Context = createContext<{ summary?: NotificationSummary; error?: Error; refresh: () => Promise<void> } | null>(null);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [summary, setSummary] = useState<NotificationSummary>();
  const [error, setError] = useState<Error>();
  const generation = useRef(0);
  const path = usePathname();
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    try {
      const data = await api<NotificationSummary>("/notifications/summary");
      if (current === generation.current) { setSummary(data); setError(undefined); }
    } catch (cause) {
      if (current === generation.current) setError(cause as Error);
    }
  }, []);
  useEffect(() => {
    const counter = generation;
    const update = () => { if (document.visibilityState === "visible") void refresh(); };
    update();
    const timer = window.setInterval(update, 30000);
    window.addEventListener("focus", update);
    window.addEventListener("notifications:changed", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      counter.current++;
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
      window.removeEventListener("notifications:changed", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [path, refresh]);
  return <Context.Provider value={{ summary, error, refresh }}>{children}</Context.Provider>;
}

export function useNotifications() {
  const context = useContext(Context);
  if (!context) throw new Error("Notifications require a workspace provider.");
  return context;
}
