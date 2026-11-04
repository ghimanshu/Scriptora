"use client";
import Link from "next/link";
import { useNotifications } from "./notification-context";
import { Icon } from "./icon";
import type { Area } from "./shell";

export function NotificationPreview({ area }: { area: Area }) {
  const { summary } = useNotifications();
  const count = summary?.unread_count;
  const recent = summary?.items.filter(item => !item.read_at).slice(0, 3) || [];
  return <section className="notification-summary" aria-label="Notification summary">
    <div className="notification-summary-heading">
      <div>
        <h2 aria-live="polite"><Icon name="bell" size={18} /> {count === undefined ? "Notifications" : `${count} unread notification${count === 1 ? "" : "s"}`}</h2>
        <p>{count === 0 ? "You are all caught up." : "Article reviews, assignments, payment decisions, and publishing updates."}</p>
      </div>
      <Link className="text-link" href={`/${area}/notifications`}>View all notifications</Link>
    </div>
    {recent.length > 0 && <ul className="notification-preview-list">{recent.map(item => <li key={item.id}>
      <strong>{item.title}</strong><span>{item.payload?.article_title || item.message}</span>
    </li>)}</ul>}
  </section>;
}
