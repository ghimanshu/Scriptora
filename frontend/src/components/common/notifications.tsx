"use client";
import { useState } from "react";
import Link from "next/link";
import { useResource, ErrorNotice, Empty, Loading } from "./data";
import { command } from "@/lib/api-client";
import { date } from "@/lib/formatting";
import type { Notification, Page } from "@/types/api";
export function Notifications() {
  const [cursor, setCursor] = useState("");
  const resource = useResource<Page<Notification>>(
    `/notifications?${new URLSearchParams({ cursor })}`,
  );
  const [error, setError] = useState<Error>();
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">STAY IN THE LOOP</div>
          <h1>Your publishing updates.</h1>
          <p>Review milestones, payment updates, and messages that matter.</p>
        </div>
      </div>
      <section className="panel">
        <ErrorNotice error={error || resource.error} retry={resource.reload} />
        {resource.loading ? (
          <Loading />
        ) : resource.data?.items.length === 0 ? (
          <Empty title="A quiet moment">
            Your publishing updates will appear here.
          </Empty>
        ) : (
          resource.data?.items.map((item) => (
            <article className="notification" key={item.id}>
              <div>
                <strong>{item.title || item.payload?.title || item.type}</strong>
                <p>{item.message || item.payload?.message}</p>
                {item.payload?.reason && <p>Reason: {item.payload.reason}</p>}
                {item.type === "REVIEWER_APPLICATION" && (
                  <Link href="/admin/users" className="text-link">Review application</Link>
                )}
                <small>{date(item.created_at)}</small>
              </div>
              {!item.read_at && (
                <button
                  className="text-link"
                  onClick={async () => {
                    try {
                      await command(`/notifications/${item.id}/read`, {});
                      await resource.reload();
                    } catch (e) {
                      setError(e as Error);
                    }
                  }}
                >
                  Mark as read
                </button>
              )}
            </article>
          ))
        )}
      </section>
      <div className="actions">
        {cursor && (
          <button className="text-link" onClick={() => setCursor("")}>
            First page
          </button>
        )}
        {resource.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(resource.data!.next_cursor!)}
          >
            Next →
          </button>
        )}
      </div>
    </>
  );
}
