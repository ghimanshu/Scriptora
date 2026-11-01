"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { command } from "@/lib/api-client";
import {
  useResource,
  Empty,
  ErrorNotice,
  Loading,
} from "@/components/common/data";
import type { Article, Assignment, Page, Taxon } from "@/types/api";
import { date } from "@/lib/formatting";
export function ReviewQueue() {
  const [subject, setSubject] = useState("");
  const [cursor, setCursor] = useState("");
  const subjects = useResource<Taxon[]>("/subjects");
  const subscriptions = useResource<string[]>("/reviewers/me/subjects");
  const queue = useResource<Page<Article>>(
    `/review-queue?${new URLSearchParams({ subject_id: subject, sort: "oldest", cursor })}`,
  );
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState("");
  const keys = useRef<Record<string, string>>({});
  const router = useRouter();
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">EXPERT PERSPECTIVES WELCOME</div>
          <h1>Find your next review.</h1>
          <p>
            Manuscripts matched to your expertise. One reviewer, one considered
            perspective.
          </p>
        </div>
        <select
          aria-label="Filter by subject"
          value={subject}
          onChange={(e) => {
            setSubject(e.target.value);
            setCursor("");
          }}
        >
          <option value="">All my subjects</option>
          {subjects.data?.filter((s) => subscriptions.data?.includes(s.id)).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Available manuscripts</h2>
            <p>
              Oldest submissions first · full manuscripts unlock after an
              eligible claim
            </p>
          </div>
          <button className="text-link" onClick={() => void queue.reload()}>
            Refresh ↻
          </button>
        </div>
        <ErrorNotice
          error={error || queue.error || subjects.error || subscriptions.error}
          retry={queue.reload}
        />
        {queue.loading ? (
          <Loading />
        ) : queue.data?.items.length === 0 ? (
          <Empty title="You’re all caught up">
            New manuscripts in your subscribed subjects will appear here.
          </Empty>
        ) : (
          queue.data?.items.map((a) => (
            <article className="queue-card" key={a.id}>
              <div className="eyebrow">
                {a.subject} · {date(a.created_at)}
              </div>
              <h3>{a.title}</h3>
              <p>{a.abstract}</p>
              <Link className="file-link" href={`/reviewer/articles/${a.id}`}>View manuscript</Link>
              {confirm === a.id ? (
                <div className="confirm-box">
                  <p>
                    By claiming, you confirm that you are eligible and have no
                    author, coauthor, or other conflict. The backend sets your
                    five-day review deadline.
                  </p>
                  <div className="actions">
                    <button
                      className="button"
                      disabled={!!busy}
                      onClick={async () => {
                        setBusy(a.id);
                        setError(undefined);
                        try {
                          keys.current[a.id] ||= crypto.randomUUID();
                          const assignment = await command<Assignment>(
                            `/articles/${a.id}/claim`,
                            {
                              expected_version: a.lock_version,
                              no_conflict: true,
                            },
                            keys.current[a.id],
                          );
                          router.push(`/reviewer/assignments/${assignment.id}`);
                        } catch (e) {
                          setError(e as Error);
                          await queue.reload();
                        } finally {
                          setBusy("");
                        }
                      }}
                    >
                      Confirm no conflict & claim
                    </button>
                    <button
                      className="text-link"
                      onClick={() => setConfirm("")}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="actions">
                  <button
                    className="button secondary small"
                    onClick={() => setConfirm(a.id)}
                  >
                    Review this manuscript →
                  </button>
                  <button
                    className="text-link"
                    onClick={async () => {
                      const reason = window.prompt(
                        "Describe your conflict of interest:",
                      );
                      if (!reason) return;
                      try {
                        await command(`/articles/${a.id}/conflicts`, {
                          reason,
                        });
                        await queue.reload();
                      } catch (e) {
                        setError(e as Error);
                      }
                    }}
                  >
                    Declare conflict
                  </button>
                </div>
              )}
            </article>
          ))
        )}
        <div className="pagination">
          <span>Eligibility and workload are verified when you claim.</span>
          <div className="actions">
            {cursor && (
              <button className="text-link" onClick={() => setCursor("")}>
                First page
              </button>
            )}
            {queue.data?.next_cursor && (
              <button
                className="text-link"
                onClick={() => setCursor(queue.data!.next_cursor!)}
              >
                Next →
              </button>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
