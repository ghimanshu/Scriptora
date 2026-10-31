"use client";
import { useState, useRef } from "react";
import { useResource, ErrorNotice, Loading } from "@/components/common/data";
import { Status } from "./article-table";
import { api, command } from "@/lib/api-client";
import { date, deadline } from "@/lib/formatting";
import { FileUpload } from "@/components/forms/file-upload";
import { Payment } from "@/components/payments/payment";
import { PublicationForm } from "@/components/payments/publication";
import type { Article, Page, Version, TimelineEvent } from "@/types/api";
export function ArticleWorkspace({
  id,
  admin = false,
}: {
  id: string;
  admin?: boolean;
}) {
  const article = useResource<Article>(`/articles/${id}`);
  const versions = useResource<Page<Version>>(`/articles/${id}/versions`);
  const timeline = useResource<Page<TimelineEvent>>(`/articles/${id}/timeline`);
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState("");
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [confirm, setConfirm] = useState(false);
  const key = useRef("");
  const a = article.data;
  return (
    <>
      <ErrorNotice error={article.error || error} retry={article.reload} />
      {article.loading && <Loading />}
      {a && (
        <>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                MANUSCRIPT WORKSPACE · VERSION {a.current_version_number}
              </div>
              <h1>{a.title || "Untitled manuscript"}</h1>
              <p>
                {a.subject} · {a.outlet} · Created {date(a.created_at)}
              </p>
            </div>
            <Status status={a.status} />
          </div>
          <div className="detail-grid">
            <div>
              <section className="panel">
                <h2>Abstract</h2>
                <p>{a.abstract || "No abstract added yet."}</p>
              </section>
              <section className="panel">
                <h2>Versions & review feedback</h2>
                <ErrorNotice error={versions.error} retry={versions.reload} />
                {versions.loading && <Loading />}
                {versions.data?.items.map((v) => (
                  <div key={v.id} className="feedback">
                    <h3>
                      Version {v.version_number}{" "}
                      <small className="subtle">{date(v.created_at)}</small>
                    </h3>
                    {v.manuscript_file_id && (
                      <a
                        className="file-link"
                        href={`/api/v1/files/${v.manuscript_file_id}/download`}
                      >
                        Download manuscript ↓
                      </a>
                    )}
                    {v.reviews?.map((r) => (
                      <div key={r.id}>
                        <strong>
                          {r.decision === "APPROVE"
                            ? "Approved"
                            : "Changes requested"}
                        </strong>
                        <p>{r.summary}</p>
                        {r.comments.map((c) => (
                          <div className="feedback" key={c.id}>
                            <small>
                              {c.section_ref} ·{" "}
                              {c.required ? "Required" : "Advisory"}
                            </small>
                            <p>{c.text}</p>
                            {a.allowed_actions.includes("RESUBMIT") &&
                              !admin && (
                                <label>
                                  Your response
                                  <textarea
                                    required={c.required}
                                    value={responses[c.id] || ""}
                                    onChange={(e) =>
                                      setResponses((previous) => ({
                                        ...previous,
                                        [c.id]: e.target.value,
                                      }))
                                    }
                                  />
                                </label>
                              )}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                ))}
              </section>
              {!admin &&
                (a.allowed_actions.includes("RESUBMIT") ||
                  a.allowed_actions.includes("EDIT")) && (
                  <section className="panel">
                    <h2>
                      {a.status === "REVIEWED"
                        ? "Prepare your revision"
                        : "Continue your draft"}
                    </h2>
                    <form
                      className="form-stack"
                      onSubmit={async (e) => {
                        e.preventDefault();
                        setBusy(true);
                        setError(undefined);
                        try {
                          const fields = new FormData(e.currentTarget);
                          if (a.status === "DRAFT") {
                            await api(`/articles/${id}`, {
                              method: "PATCH",
                              headers: { "If-Match": String(a.lock_version) },
                              body: JSON.stringify({
                                title: fields.get("title"),
                                abstract: fields.get("abstract"),
                                ...(file ? { manuscript_file_id: file } : {}),
                              }),
                            });
                          } else {
                            if (!confirm || !file)
                              throw new Error(
                                "Upload your revised manuscript and confirm the submission.",
                              );
                            const working = await api<Version>(
                              `/articles/${id}/versions`,
                              {
                                method: "POST",
                                body: JSON.stringify({
                                  manuscript_file_id: file,
                                  change_summary: summary,
                                }),
                              },
                            );
                            key.current ||= crypto.randomUUID();
                            await command(
                              `/articles/${id}/resubmit`,
                              {
                                new_version_id: working.id,
                                response_map: responses,
                                expected_version: a.lock_version,
                              },
                              key.current,
                            );
                          }
                          await article.reload();
                          await versions.reload();
                          await timeline.reload();
                        } catch (e) {
                          setError(e as Error);
                          await article.reload();
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {a.status === "DRAFT" ? (
                        <>
                          <label>
                            Title
                            <input
                              name="title"
                              defaultValue={a.title}
                              required
                            />
                          </label>
                          <label>
                            Abstract
                            <textarea
                              name="abstract"
                              defaultValue={a.abstract}
                              required
                            />
                          </label>
                        </>
                      ) : (
                        <label>
                          Revision summary
                          <textarea
                            required
                            value={summary}
                            onChange={(e) => setSummary(e.target.value)}
                          />
                        </label>
                      )}
                      <FileUpload
                        articleId={id}
                        onUploaded={(f) => setFile(f.id)}
                      />
                      {a.status === "REVIEWED" && (
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            required
                            checked={confirm}
                            onChange={(e) => setConfirm(e.target.checked)}
                          />
                          I confirm the revised manuscript and responses are
                          ready to submit.
                        </label>
                      )}
                      <button className="button" disabled={busy}>
                        {busy
                          ? "Saving…"
                          : a.status === "DRAFT"
                            ? "Save draft changes"
                            : "Confirm & resubmit revision"}
                      </button>
                    </form>
                  </section>
                )}
              {!admin && a.allowed_actions.includes("SUBMIT") && (
                <section className="panel">
                  <h2>Submit manuscript</h2>
                  <p>
                    This freezes the current version and sends it for expert
                    review.
                  </p>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={confirm}
                      onChange={(e) => setConfirm(e.target.checked)}
                    />
                    I confirm this manuscript is ready to submit.
                  </label>
                  <button
                    style={{ marginTop: 15 }}
                    className="button"
                    disabled={!confirm || busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        key.current ||= crypto.randomUUID();
                        await command(
                          `/articles/${id}/submit`,
                          { expected_version: a.lock_version },
                          key.current,
                        );
                        await article.reload();
                      } catch (e) {
                        setError(e as Error);
                        await article.reload();
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Confirm submission
                  </button>
                </section>
              )}
              {a.allowed_actions.includes("VIEW_INVOICE") && (
                <Payment articleId={id} admin={admin} />
              )}{" "}
              {admin && a.allowed_actions.includes("PUBLISH") && (
                <PublicationForm article={a} onDone={article.reload} />
              )}{" "}
              {admin && a.allowed_actions.includes("REASSIGN") && (
                <AdminAssignment article={a} onDone={article.reload} />
              )}
            </div>
            <aside>
              <section className="panel">
                <h2>At a glance</h2>
                <dl className="meta-list">
                  <div>
                    <dt>Current version</dt>
                    <dd>v{a.current_version_number}</dd>
                  </div>
                  <div>
                    <dt>Subject</dt>
                    <dd>{a.subject || "Not set"}</dd>
                  </div>
                  {a.assignment && (
                    <>
                      <div>
                        <dt>Assignment</dt>
                        <dd>{a.assignment.state}</dd>
                      </div>
                      <div>
                        <dt>Review deadline</dt>
                        <dd>
                          {deadline(a.assignment.due_at)}
                          <br />
                          <small title={a.assignment.due_at}>
                            UTC: {a.assignment.due_at}
                          </small>
                        </dd>
                      </div>
                    </>
                  )}
                </dl>
              </section>
              <section className="panel">
                <h2>Activity</h2>
                <ErrorNotice error={timeline.error} retry={timeline.reload} />
                <ul className="timeline">
                  {timeline.data?.items.map((event) => (
                    <li key={event.id}>
                      <strong>{event.label || event.event_type}</strong>
                      <small>{date(event.created_at)}</small>
                      <p>{event.description}</p>
                    </li>
                  ))}
                </ul>
              </section>
            </aside>
          </div>
        </>
      )}
    </>
  );
}
function AdminAssignment({
  article,
  onDone,
}: {
  article: Article;
  onDone: () => void;
}) {
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  return (
    <section className="panel">
      <h2>Reassign review</h2>
      <ErrorNotice error={error} />
      <form
        className="form-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          setBusy(true);
          try {
            await command(`/admin/articles/${article.id}/reassign`, {
              reviewer_id: data.get("reviewer_id") || undefined,
              return_to_pool: !data.get("reviewer_id"),
              reason: data.get("reason"),
              expected_version: article.lock_version,
            });
            onDone();
          } catch (e) {
            setError(e as Error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Reviewer account ID{" "}
          <small>Leave blank to return to the eligible pool.</small>
          <input name="reviewer_id" />
        </label>
        <label>
          Reason
          <textarea name="reason" required />
        </label>
        <button className="button secondary" disabled={busy}>
          Reassign with reason
        </button>
      </form>
      {article.assignment && (
        <form
          className="form-stack"
          style={{ marginTop: 25 }}
          onSubmit={async (e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            setBusy(true);
            try {
              await command(
                `/admin/assignments/${article.assignment!.id}/extend`,
                {
                  new_due_at: new Date(String(data.get("due"))).toISOString(),
                  reason: data.get("reason"),
                },
              );
              onDone();
            } catch (e) {
              setError(e as Error);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h3>Extend live assignment</h3>
          <label>
            New deadline (your local time)
            <input name="due" type="datetime-local" required />
          </label>
          <label>
            Reason
            <textarea name="reason" required />
          </label>
          <button className="button secondary" disabled={busy}>
            Save deadline extension
          </button>
        </form>
      )}
    </section>
  );
}
