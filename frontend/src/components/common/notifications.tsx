"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useResource, ErrorNotice, Empty, Loading } from "./data";
import { useNotifications } from "./notification-context";
import { command } from "@/lib/api-client";
import type { Notification, NotificationPage } from "@/types/api";

export function Notifications() {
  const [view, setView] = useState({ status: "all", cursor: "" });
  const resource = useResource<NotificationPage>(`/notifications?${new URLSearchParams(view)}`);
  const reload = resource.reload;
  useEffect(() => {
    const update = () => { if (document.visibilityState === "visible") void reload(); };
    const timer = window.setInterval(update, 30000);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [reload]);
  const { summary, refresh } = useNotifications();
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState("");
  const router = useRouter();
  const unread = resource.data?.unread_count ?? summary?.unread_count ?? 0;
  const change = async (item: Notification, read: boolean, open = false) => {
    setBusy(item.id);
    setError(undefined);
    try {
      await command(`/notifications/${item.id}/${read ? "read" : "unread"}`, {});
      if (open && item.href) router.push(item.href);
      else await resource.reload();
    } catch (cause) { setError(cause as Error); }
    finally { setBusy(""); }
  };
  return <>
    <div className="page-heading">
      <div><div className="eyebrow">STAY IN THE LOOP</div><h1>Notifications</h1>
        <p aria-live="polite">{unread} unread notification{unread === 1 ? "" : "s"}</p></div>
      <button className="button secondary" disabled={!!busy || unread === 0} onClick={async () => {
        setBusy("all"); setError(undefined);
        try { await command("/notifications/read-all", {}); await resource.reload(); }
        catch (cause) { setError(cause as Error); }
        finally { setBusy(""); }
      }}>Mark all as read</button>
    </div>
    <div className="notification-toolbar">
      <div className="tabs" role="group" aria-label="Filter notifications">
        {["all", "unread", "read"].map(status => <button key={status} type="button"
          aria-pressed={view.status === status} className={view.status === status ? "selected" : undefined}
          onClick={() => setView({ status, cursor: "" })}>{status[0].toUpperCase() + status.slice(1)}</button>)}
      </div>
      <button className="text-link" onClick={() => { void resource.reload(); void refresh(); }}>Refresh notifications</button>
    </div>
    <section className="panel">
      <ErrorNotice error={error || resource.error} retry={resource.reload} />
      {resource.loading ? <Loading /> : resource.data?.items.length === 0 ? <Empty title={view.status === "unread" ? "No unread notifications" : "No notifications to display"}>Your publishing updates will appear here.</Empty> :
        resource.data?.items.map(item => <article className={`notification ${item.read_at ? "is-read" : "is-unread"}`} key={item.id}>
          <div className="notification-content">
            <div className="notification-title"><strong>{item.title || item.payload?.title || item.type}</strong><span className={`badge ${item.read_at ? "" : "unread-status"}`}>{item.read_at ? "Read" : "Unread"}</span></div>
            <p>{item.message || item.payload?.message}</p>
            {item.payload?.article_title && <p>Article: {item.payload.article_title}</p>}
            {item.payload?.reason && <p>Reason: {item.payload.reason}</p>}
            <small>{new Date(item.created_at).toLocaleString()}</small>
            {item.href && <Link href={item.href} className="file-link" onClick={event => {
              if (!item.read_at) { event.preventDefault(); void change(item, true, true); }
            }}>View details</Link>}
          </div>
          <button className="text-link" disabled={!!busy} onClick={() => void change(item, !item.read_at)}
            aria-label={`${item.read_at ? "Mark as unread" : "Mark as read"}: ${item.title}`}>{item.read_at ? "Mark as unread" : "Mark as read"}</button>
        </article>)}
    </section>
    <div className="actions">
      {view.cursor && <button className="text-link" onClick={() => setView(previous => ({ ...previous, cursor: "" }))}>Newest notifications</button>}
      {resource.data?.next_cursor && <button className="button secondary" onClick={() => setView(previous => ({ ...previous, cursor: resource.data!.next_cursor! }))}>Older notifications</button>}
    </div>
  </>;
}
