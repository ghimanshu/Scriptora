"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import {
  useResource,
  ErrorNotice,
  Loading,
  Empty,
} from "@/components/common/data";
import { api, command } from "@/lib/api-client";
import { deadline } from "@/lib/formatting";
import type { Assignment, Article, Page, Version } from "@/types/api";
export function ReviewWorkspace({ id }: { id: string }) {
  const [cursor, setCursor] = useState("");
  const assignments = useResource<Page<Assignment>>(
    `/assignments/me?${new URLSearchParams({ cursor })}`,
  );
  const assignment = assignments.data?.items.find((a) => a.id === id);
  const article = useResource<Article>(
    assignment ? `/articles/${assignment.article_id}` : null,
  );
  const versions = useResource<Page<Version>>(
    assignment ? `/articles/${assignment.article_id}/versions` : null,
  );
  const [summary, setSummary] = useState("");
  const [comments, setComments] = useState<
    {
      client_id: string;
      section_ref: string;
      text: string;
      required: boolean;
    }[]
  >([]);
  const [decision, setDecision] = useState("REQUEST_REVISION");
  const [format, setFormat] = useState(false);
  const [references, setReferences] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [saved, setSaved] = useState("");
  const key = useRef("");
  const payload = () => ({
    decision,
    expected_article_version: article.data?.lock_version,
    summary,
    checklist: { format_valid: format, references_checked: references },
    comments,
  });
  const live = assignment?.state === "ACTIVE";
  const reload = async () => {
    await assignments.reload();
    await article.reload();
  };
  return (
    <>
      <ErrorNotice
        error={assignments.error || article.error || error}
        retry={reload}
      />
      {assignments.loading && <Loading />}
      {assignments.data && !assignment && (
        <Empty title="Assignment not on this page">
          {assignments.data.next_cursor ? (
            <button
              className="button secondary"
              onClick={() => setCursor(assignments.data!.next_cursor!)}
            >
              Search next assignments page →
            </button>
          ) : (
            "This assignment is unavailable. Return to your assignments list."
          )}
        </Empty>
      )}
      {assignment && (
        <>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                REVIEW WORKSPACE · {assignment.state}
              </div>
              <h1>
                {article.data?.title || assignment.title || "Manuscript review"}
              </h1>
              <p>
                Due {deadline(assignment.due_at)} · UTC: {assignment.due_at}
              </p>
            </div>
            <Link className="text-link" href="/reviewer/assignments">
              ← My assignments
            </Link>
          </div>
          <div className="detail-grid">
            <div>
              <section className="panel">
                <h2>Manuscript & prior reviews</h2>
                <p>{article.data?.abstract}</p>
                <ErrorNotice error={versions.error} retry={versions.reload} />
                {versions.data?.items.map((v) => (
                  <div className="feedback" key={v.id}>
                    <h3>Version {v.version_number}</h3>
                    {v.manuscript_file_id && (
                      <a
                        className="file-link"
                        href={`/api/v1/files/${v.manuscript_file_id}/download`}
                      >
                        Download version {v.version_number} ↓
                      </a>
                    )}
                    {v.reviews?.map((r) => (
                      <div key={r.id}>
                        <strong>{r.decision}</strong>
                        <p>{r.summary}</p>
                        {r.comments.map((c) => (
                          <p key={c.id}>
                            {c.section_ref}: {c.text}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                ))}
              </section>
              {assignment.state === "RESERVED" && (
                <section className="panel">
                  <h2>Your reserved revision is ready</h2>
                  <p>Starting the review preserves the existing deadline.</p>
                  <button
                    className="button"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await command(`/assignments/${id}/start`, {});
                        await reload();
                      } catch (e) {
                        setError(e as Error);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Start reserved review
                  </button>
                </section>
              )}
              {live && (
                <section className="panel">
                  <h2>A thoughtful, actionable review</h2>
                  <form
                    className="form-stack"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      setBusy(true);
                      setError(undefined);
                      try {
                        if (!confirm)
                          throw new Error("Confirm your final decision first.");
                        key.current ||= crypto.randomUUID();
                        await command(
                          `/assignments/${id}/review`,
                          payload(),
                          key.current,
                        );
                        setSaved(
                          "Review submitted. Thank you for your perspective.",
                        );
                        await reload();
                      } catch (e) {
                        setError(e as Error);
                        await reload();
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <label>
                      Overall feedback
                      <textarea
                        required
                        value={summary}
                        onChange={(e) => setSummary(e.target.value)}
                      />
                    </label>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={format}
                        onChange={(e) => setFormat(e.target.checked)}
                      />
                      Formatting and submission requirements checked
                    </label>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={references}
                        onChange={(e) => setReferences(e.target.checked)}
                      />
                      References checked
                    </label>
                    <h3>Structured comments</h3>
                    {comments.map((c, i) => (
                      <div className="feedback form-stack" key={c.client_id}>
                        <label>
                          Section or page reference
                          <input
                            required
                            value={c.section_ref}
                            onChange={(e) =>
                              setComments((previous) =>
                                previous.map((item, index) =>
                                  index === i
                                    ? { ...item, section_ref: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                        </label>
                        <label>
                          Comment
                          <textarea
                            required
                            value={c.text}
                            onChange={(e) =>
                              setComments((previous) =>
                                previous.map((item, index) =>
                                  index === i
                                    ? { ...item, text: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                        </label>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={c.required}
                            onChange={(e) =>
                              setComments((previous) =>
                                previous.map((item, index) =>
                                  index === i
                                    ? { ...item, required: e.target.checked }
                                    : item,
                                ),
                              )
                            }
                          />
                          Required change
                        </label>
                        <button
                          type="button"
                          className="text-link"
                          onClick={() =>
                            setComments((previous) =>
                              previous.filter(
                                (item) => item.client_id !== c.client_id,
                              ),
                            )
                          }
                        >
                          Remove comment
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="button secondary"
                      onClick={() =>
                        setComments((previous) => [
                          ...previous,
                          {
                            client_id: crypto.randomUUID(),
                            section_ref: "",
                            text: "",
                            required: true,
                          },
                        ])
                      }
                    >
                      + Add comment
                    </button>
                    <label>
                      Editorial decision
                      <select
                        value={decision}
                        onChange={(e) => {
                          setDecision(e.target.value);
                          setConfirm(false);
                        }}
                      >
                        <option value="REQUEST_REVISION">
                          Request revision
                        </option>
                        <option value="APPROVE">Approve manuscript</option>
                      </select>
                    </label>
                    <div className="confirm-box">
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          required
                          checked={confirm}
                          onChange={(e) => setConfirm(e.target.checked)}
                        />
                        I confirm this final review applies to version{" "}
                        {article.data?.current_version_number}. Submitted
                        feedback becomes immutable.
                      </label>
                    </div>
                    <div className="actions">
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            await api(`/assignments/${id}/review-draft`, {
                              method: "PUT",
                              body: JSON.stringify(payload()),
                            });
                            setSaved("Feedback draft saved.");
                          } catch (e) {
                            setError(e as Error);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        Save feedback draft
                      </button>
                      <button className="button" disabled={busy || !confirm}>
                        Confirm & submit review
                      </button>
                    </div>
                  </form>
                </section>
              )}
              {saved && (
                <div className="notice success" role="status">
                  {saved}
                </div>
              )}
            </div>
            <aside>
              <section className="panel">
                <h2>Review deadline</h2>
                <p>{deadline(assignment.due_at)}</p>
                <p className="subtle">UTC: {assignment.due_at}</p>
                <p>
                  The backend enforces the exact deadline. A draft does not
                  extend your assignment.
                </p>
                {["ACTIVE", "RESERVED"].includes(assignment.state) && (
                  <form
                    className="form-stack"
                    style={{ marginTop: 20 }}
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const reason = new FormData(e.currentTarget).get(
                        "reason",
                      );
                      setBusy(true);
                      try {
                        await command(`/assignments/${id}/release`, { reason });
                        await reload();
                      } catch (e) {
                        setError(e as Error);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <label>
                      Return assignment with reason
                      <textarea name="reason" required />
                    </label>
                    <button className="button secondary" disabled={busy}>
                      Return to review pool
                    </button>
                  </form>
                )}
              </section>
            </aside>
          </div>
        </>
      )}
    </>
  );
}
