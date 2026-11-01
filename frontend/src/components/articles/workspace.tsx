"use client";
import { useState, useRef } from "react";
import { useResource, ErrorNotice, Loading } from "@/components/common/data";
import { Status } from "./article-table";
import { DeleteArticle } from "./delete-article";
import { api, command } from "@/lib/api-client";
import { date, deadline } from "@/lib/formatting";
import { FileUpload } from "@/components/forms/file-upload";
import { Payment } from "@/components/payments/payment";
import { PublicationForm } from "@/components/payments/publication";
import type { Article, Page, Version, TimelineEvent, Taxon } from "@/types/api";
export function ArticleWorkspace({
  id,
  admin = false,
}: {
  id: string;
  admin?: boolean;
}) {
  const article = useResource<Article>(`/articles/${id}`);
  const versions = useResource<Version[] | Page<Version>>(`/articles/${id}/versions`);
  const timeline = useResource<TimelineEvent[] | Page<TimelineEvent>>(`/articles/${id}/timeline`);
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState("");
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState(false);
  const key = useRef("");
  const draftForm = useRef<HTMLFormElement>(null);
  const a = article.data;
  const allowedActions = Array.isArray(a?.allowed_actions) ? a.allowed_actions : [];
  const canEditDraft = !admin && a?.status === "DRAFT" && allowedActions.includes("EDIT");
  const canRevise = !admin && a?.status === "REJECTED" && allowedActions.includes("RESUBMIT");
  const subjects = useResource<Taxon[]>(canEditDraft ? "/subjects" : null);
  const versionItems = Array.isArray(versions.data) ? versions.data : versions.data?.items;
  const timelineItems = Array.isArray(timeline.data) ? timeline.data : timeline.data?.items;
  async function saveDraft(fields: FormData) {
    if (!a?.current_version) {
      throw new Error("Reload the article before saving your draft.");
    }
    const metadata = {
      ...a.current_version.data,
      title: String(fields.get("title") || ""),
      abstract: String(fields.get("abstract") || ""),
    };
    return api<Article>(`/articles/${id}`, {
      method: "PATCH",
      headers: {
        "If-Match": String(a.lock_version),
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        metadata,
        ...(subjects.data ? { primary_subject_id: fields.get("primary_subject_id") || null } : {}),
        manuscript_file_id: file || a.current_version.manuscript_file_id || null,
      }),
    });
  }
  return (
    <>
      <ErrorNotice error={article.error || subjects.error || error} retry={article.reload} />
      {article.loading && <Loading />}
      {a && (
        <>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                MANUSCRIPT WORKSPACE Â· VERSION {a.current_version_number}
              </div>
              <h1>{a.title || "Untitled manuscript"}</h1>
              <p>
                {a.subject} Â· {a.outlet} Â· Created {date(a.created_at)}
              </p>
            </div>
            <Status status={a.status} />
          </div>
          <div className="detail-grid">
            <div>
              {!admin && !canEditDraft && !canRevise && (
                <div className="notice" role="status">
                  This article is read-only. Editing becomes available when a reviewer requests changes.
                </div>
              )}
              <section className="panel">
                <h2>Abstract</h2>
                <p>{a.abstract || "No abstract added yet."}</p>
              </section>
              <section className="panel">
                <h2>Versions & review feedback</h2>
                <ErrorNotice error={versions.error} retry={versions.reload} />
                {versions.loading && <Loading />}
                {versionItems?.map((v) => (
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
                        Download manuscript â†“
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
                              {c.section_ref} Â·{" "}
                              {c.required ? "Required" : "Advisory"}
                            </small>
                            <p>{c.text}</p>
                            {canRevise && v.id === a.current_version_id && r.decision === "REQUEST_REVISION" && (
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
              {(canEditDraft || canRevise) && (
                  <section className="panel">
                    <h2>
                      {a.status === "REJECTED"
                        ? "Prepare your revision"
                        : "Continue your draft"}
                    </h2>
                    {canRevise && (
                      <p>Address the review comments and edit your article. You can replace the manuscript below. Resubmitting starts a new five-day review with the previous reviewer when they are available.</p>
                    )}
                    <form
                      ref={draftForm}
                      className="form-stack"
                      onSubmit={async (e) => {
                        e.preventDefault();
                        setBusy(true);
                        setError(undefined);
                        try {
                          const fields = new FormData(e.currentTarget);
                          if (a.status === "DRAFT") {
                            await saveDraft(fields);
                          } else {
                            if (!confirm)
                              throw new Error(
                                "Confirm your revised manuscript and responses before submitting.",
                              );
                            if (!a.current_version) throw new Error("Reload the article before revising.");
                            const manuscriptFile = file || a.current_version.manuscript_file_id;
                            if (!manuscriptFile) throw new Error("Upload a manuscript before resubmitting.");
                            const working = await command<Version>(
                              `/articles/${id}/versions`,
                              {
                                metadata: {
                                  ...a.current_version.data,
                                  title: String(fields.get("title") || ""),
                                  abstract: String(fields.get("abstract") || ""),
                                },
                                manuscript_file_id: manuscriptFile,
                              },
                            );
                            await command(
                              `/articles/${id}/resubmit`,
                              {
                                new_version_id: working.id,
                                responses,
                                expected_version: a.lock_version,
                              },
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
                      <>
                          {canEditDraft && (
                            <label>
                              Primary subject
                              <select key={String(subjects.loading)} name="primary_subject_id" defaultValue={a.primary_subject_id || ""} disabled={subjects.loading}>
                                <option value="">Choose a subject before submitting</option>
                                {subjects.data?.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
                              </select>
                            </label>
                          )}
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
                      <FileUpload
                        articleId={id}
                        onUploaded={(f) => setFile(f.id)}
                      />
                      {a.status === "REJECTED" && (
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
                          ? "Savingâ€¦"
                          : a.status === "DRAFT"
                            ? "Save draft changes"
                            : "Confirm & resubmit revision"}
                      </button>
                    </form>
                  </section>
                )}
              {canEditDraft && allowedActions.includes("SUBMIT") && (
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
                        if (!file && !a.current_version?.manuscript_file_id) {
                          throw new Error("Upload a manuscript before submitting.");
                        }
                        const fields = draftForm.current
                          ? new FormData(draftForm.current)
                          : new FormData();
                        if (!fields.get("primary_subject_id"))
                          throw new Error("Choose a primary subject before submitting for review.");
                        const saved = await saveDraft(fields);
                        key.current ||= crypto.randomUUID();
                        await command(
                          `/articles/${id}/submit`,
                          { expected_version: saved.lock_version },
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
              {allowedActions.includes("VIEW_INVOICE") && (
                <Payment articleId={id} admin={admin} onDone={article.reload} />
              )}{" "}
              {admin && allowedActions.includes("PUBLISH") && (
                <PublicationForm article={a} onDone={article.reload} />
              )}{" "}
              {admin && <DeleteArticle articleId={id} />}
              {admin && allowedActions.includes("ASSIGN") && (
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
                  {timelineItems?.map((event) => (
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
function AdminAssignment({ article, onDone }: { article: Article; onDone: () => void }) {
  const candidates = useResource<Page<{ id: string; name: string; email: string }>>(
    `/admin/articles/${article.id}/reviewers`,
  );
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  return (
    <section className="panel form-panel">
      <h2>Assign a reviewer</h2>
      <p>Select an eligible reviewer in the same subject. The review is due in five days.</p>
      <ErrorNotice error={error || candidates.error} retry={candidates.reload} />
      {candidates.loading && <Loading />}
      {candidates.data?.items.length === 0 && <p>No eligible reviewers are currently available.</p>}
      <form className="form-stack" onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError(undefined);
        const fields = new FormData(event.currentTarget);
        try {
          await command(`/admin/articles/${article.id}/assign`, {
            reviewer_id: fields.get("reviewer_id"), reason: fields.get("reason"),
            expected_version: article.lock_version,
          });
          onDone();
        } catch (error) {
          setError(error as Error);
        } finally { setBusy(false); }
      }}>
        <label>Reviewer
          <select name="reviewer_id" required disabled={busy || candidates.loading} defaultValue="">
            <option value="" disabled>Select a reviewer</option>
            {candidates.data?.items.map((reviewer) => <option key={reviewer.id} value={reviewer.id}>{reviewer.name} ({reviewer.email})</option>)}
          </select>
        </label>
        <label>Assignment reason<textarea name="reason" required minLength={3} /></label>
        <button className="button" disabled={busy || !candidates.data?.items.length}>Assign reviewer</button>
      </form>
    </section>
  );
}
