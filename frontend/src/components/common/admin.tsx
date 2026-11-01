"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useResource, ErrorNotice, Empty, Loading } from "./data";
import { api, command } from "@/lib/api-client";
import { PaymentDecision } from "@/components/payments/payment";
import { money, date } from "@/lib/formatting";
import type { Page, PaymentAttempt, User, Taxon } from "@/types/api";
export function AdminPayments() {
  const result = useResource<PaymentAttempt[]>("/admin/payments");
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">PAYMENT RECONCILIATION</div>
          <h1>A careful check before the next chapter.</h1>
          <p>
            Verify actual bank receipts. Screenshots alone are supporting
            evidence.
          </p>
        </div>
      </div>
      <ErrorNotice error={result.error} retry={result.reload} />
      {result.loading ? (
        <Loading />
      ) : result.data?.length === 0 ? (
        <section className="panel">
          <Empty title="All caught up">
            Payment proofs awaiting verification will appear here.
          </Empty>
        </section>
      ) : (
        result.data?.map((attempt) => (
          <section className="panel form-panel" key={attempt.id}>
            <div className="panel-heading">
              <h2>{money(attempt.amount_minor, attempt.currency)}</h2>
              <span className="badge">{attempt.status}</span>
            </div>
            <p className="subtle">Reference: {attempt.reference}</p>
            <a
              className="file-link"
              href={`/api/v1/files/${attempt.proof_file_id}/download`}
            >
              Download proof ↓
            </a>
            {attempt.article_id && (
              <Link
                className="file-link"
                href={`/admin/articles/${attempt.article_id}`}
              >
                Open manuscript →
              </Link>
            )}
            {attempt.status === "SUBMITTED" && (
              <PaymentDecision attempt={attempt} onDone={result.reload} />
            )}
          </section>
        ))
      )}
    </>
  );
}
export function AdminPeople() {
  const [cursor, setCursor] = useState("");
  const users = useResource<
    Page<Omit<User, "roles"> & { roles?: User["roles"] | null; active: boolean }>
  >(
    `/admin/users?${new URLSearchParams({ cursor })}`,
  );
  const reviewers = useResource<Page<User & { email_verified: boolean; active: boolean }>>("/admin/reviewers");
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">PEOPLE & PERMISSIONS</div>
          <h1>A community of considered voices.</h1>
          <p>Manage accounts, approve reviewers, and invite subject experts.</p>
        </div>
      </div>
      <ErrorNotice
        error={error || users.error || reviewers.error}
        retry={() => {
          void users.reload();
          void reviewers.reload();
        }}
      />
      {message && (
        <div className="notice success" role="status">
          {message}
        </div>
      )}
      <div className="settings-grid">
        <section className="panel">
          <h2>Invite a reviewer</h2>
          <form
            className="form-stack"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              const data = new FormData(e.currentTarget);
              try {
                await command("/admin/reviewer-invitations", {
                  email: data.get("email"),
                  subject_ids: String(data.get("subjects"))
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setMessage("Reviewer invitation created.");
              } catch (e) {
                setError(e as Error);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Email address
              <input name="email" type="email" required />
            </label>
            <label>
              Permitted subject IDs, comma separated
              <input name="subjects" required />
            </label>
            <button className="button" disabled={busy}>
              Send reviewer invitation
            </button>
          </form>
        </section>
        <section className="panel">
          <h2>Reviewer approval</h2>
          {reviewers.loading && <Loading />}
          {reviewers.data?.items.map((user) => (
            <div className="assignment-row" key={user.id}>
              <div>
                <strong>{user.name}</strong>
                <p>{user.email}</p>
                <small>Awaiting admin decision</small>
                {!user.active && <small>Account inactive</small>}
              </div>
              <button
                className="button secondary small"
                disabled={busy || !user.active}
                onClick={async () => {
                  const reason = window.prompt(
                    `Reason for approving ${user.name} as reviewer:`,
                  );
                  if (!reason?.trim()) return;
                  setError(undefined);
                  setBusy(true);
                  try {
                    await command(`/admin/reviewers/${user.id}/approve`, {
                      reason,
                    });
                    setMessage("Reviewer approval recorded. Decision email queued.");
                    await reviewers.reload();
                    await users.reload();
                  } catch (e) {
                    setError(e as Error);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Approve
              </button>
              <button
                className="button secondary small"
                disabled={busy || !user.active}
                onClick={async () => {
                  const reason = window.prompt(`Reason for rejecting ${user.name} as reviewer:`);
                  if (!reason?.trim()) return;
                  setError(undefined);
                  setBusy(true);
                  try {
                    await command(`/admin/reviewers/${user.id}/reject`, { reason });
                    setMessage("Reviewer application rejected. Decision email queued.");
                    await reviewers.reload();
                    await users.reload();
                  } catch (e) {
                    setError(e as Error);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Reject
              </button>
            </div>
          ))}
          {reviewers.data?.items.length === 0 && (
            <p className="subtle">No reviewers to display.</p>
          )}
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Accounts</h2>
          <span className="subtle">
            Backend enforces role changes and final-admin protection.
          </span>
        </div>
        {users.loading && <Loading />}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>ACCOUNT</th>
                <th>ROLES</th>
                <th>STATUS</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.items.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.name}</strong>
                    <small>{user.email}</small>
                  </td>
                  <td>{user.roles?.join(", ") || "Not provided"}</td>
                  <td>{user.active ? "Active" : "Inactive"}</td>
                  <td>
                    <button
                      className="text-link"
                      disabled={busy}
                      onClick={async () => {
                        const reason = window.prompt(
                          `Reason to ${user.active ? "disable" : "enable"} ${user.name}:`,
                        );
                        if (!reason) return;
                        setBusy(true);
                        try {
                          await api(`/admin/users/${user.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                              active: !user.active,
                              reason,
                            }),
                          });
                          await users.reload();
                        } catch (e) {
                          setError(e as Error);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {user.active ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          <span>{users.data?.items.length || 0} accounts on this page</span>
          <div className="actions">
            {cursor && (
              <button className="text-link" onClick={() => setCursor("")}>
                First page
              </button>
            )}
            {users.data?.next_cursor && (
              <button
                className="text-link"
                onClick={() => setCursor(users.data!.next_cursor!)}
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
export function AdminSettings() {
  const [activeTab, setActiveTab] = useState(0);
  const tabs = [
    { id: "workflow", label: "Workflow settings", content: <SettingsEditor /> },
    { id: "subjects", label: "Subjects", content: <Taxonomy kind="subjects" /> },
    { id: "outlets", label: "Publication outlets", content: <Taxonomy kind="outlets" /> },
    { id: "templates", label: "Templates", content: <RecordEditor kind="templates" title="Versioned templates" /> },
    { id: "issues", label: "Journal issues", content: <RecordEditor kind="issues" title="Journal issues" /> },
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">PUBLICATION CONFIGURATION</div>
          <h1>A thoughtful foundation.</h1>
          <p>
            Changes apply to new assignments and invoices. Existing snapshots
            retain their values.
          </p>
        </div>
      </div>
      <div className="tabs settings-tabs" role="tablist" aria-label="Admin settings">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`settings-tab-${tab.id}`}
            aria-controls={`settings-panel-${tab.id}`}
            aria-selected={activeTab === index}
            tabIndex={activeTab === index ? 0 : -1}
            className={activeTab === index ? "selected" : undefined}
            onClick={() => setActiveTab(index)}
            onKeyDown={(event) => {
              let next = index;
              if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
              else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = tabs.length - 1;
              else return;
              event.preventDefault();
              setActiveTab(next);
              document.getElementById(`settings-tab-${tabs[next].id}`)?.focus();
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab, index) => (
        <div
          key={tab.id}
          className="settings-tab-panel"
          role="tabpanel"
          id={`settings-panel-${tab.id}`}
          aria-labelledby={`settings-tab-${tab.id}`}
          hidden={activeTab !== index}
          tabIndex={0}
        >
          {tab.content}
        </div>
      ))}
    </>
  );
}
function SettingsEditor() {
  const resource = useResource<{ version: number; values: {
    publication_fee_minor: number; payment_instructions: string; max_live_assignments: number;
  } }>("/admin/settings");
  const [error, setError] = useState<Error>();
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <section className="panel">
      <h2>Workflow settings</h2>
      <ErrorNotice error={error || resource.error} retry={resource.reload} />
      {resource.loading && <Loading />}
      {saved && <p role="status" className="subtle">Settings saved. Existing invoices keep their original fee.</p>}
      {resource.data && (
        <form className="form-stack" key={resource.data.version} onSubmit={async event => {
          event.preventDefault();
          setError(undefined);
          setSaved(false);
          setBusy(true);
          const fields = new FormData(event.currentTarget);
          try {
            await command("/admin/settings", {
              review_duration_hours: 120,
              publication_fee_minor: Math.round(Number(fields.get("fee")) * 100),
              max_live_assignments: Number(fields.get("capacity")),
              payment_instructions: String(fields.get("instructions")),
            });
            setSaved(true);
            await resource.reload();
          } catch (error) { setError(error as Error); }
          finally { setBusy(false); }
        }}>
          <label>Review deadline<input value="5 days from assignment" readOnly /></label>
          <label>Publication fee (INR)<input name="fee" type="number" required min="0.01" step="0.01" defaultValue={resource.data.values.publication_fee_minor / 100} /></label>
          <label>Maximum active assignments per reviewer<input name="capacity" type="number" required min={1} max={100} defaultValue={resource.data.values.max_live_assignments} /></label>
          <label>Payment instructions<textarea name="instructions" required minLength={5} maxLength={4000} defaultValue={resource.data.values.payment_instructions} /></label>
          <button className="button" disabled={busy}>Save settings</button>
        </form>
      )}
    </section>
  );
}
function Taxonomy({ kind }: { kind: "subjects" | "outlets" }) {
  const result = useResource<Page<Taxon & { active: boolean }>>(
    `/admin/${kind}`,
  );
  const [error, setError] = useState<Error>();
  return (
    <section className="panel">
      <h2>{kind === "subjects" ? "Subjects" : "Publication outlets"}</h2>
      <ErrorNotice error={error || result.error} retry={result.reload} />
      {result.data?.items.map((item) => (
        <div className="assignment-row" key={item.id}>
          <div>
            <strong>{item.name}</strong>
            <p>{item.id}</p>
          </div>
          <button
            className="text-link"
            onClick={async () => {
              try {
                await api(`/admin/${kind}/${item.id}`, {
                  method: "PATCH",
                  body: JSON.stringify({ active: !item.active }),
                });
                await result.reload();
              } catch (e) {
                setError(e as Error);
              }
            }}
          >
            {item.active ? "Deactivate" : "Activate"}
          </button>
        </div>
      ))}
      <form
        className="form-stack"
        style={{ marginTop: 20 }}
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          try {
            await api(`/admin/${kind}`, {
              method: "POST",
              body: JSON.stringify({ name: new FormData(form).get("name") }),
            });
            form.reset();
            await result.reload();
          } catch (e) {
            setError(e as Error);
          }
        }}
      >
        <label>
          Name
          <input name="name" required maxLength={150} />
        </label>
        <button className="button secondary">
          Add {kind === "subjects" ? "subject" : "outlet"}
        </button>
      </form>
    </section>
  );
}
function RecordEditor({ kind, title }: { kind: string; title: string }) {
  const result = useResource<Page<Record<string, unknown>>>(`/admin/${kind}`);
  const [error, setError] = useState<Error>();
  const key = useRef("");
  return (
    <section className="panel">
      <h2>{title}</h2>
      <ErrorNotice error={error || result.error} retry={result.reload} />
      {result.data?.items.map((item, index) => (
        <details key={String(item.id || index)}>
          <summary>{String(item.name || item.title || item.id)}</summary>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
            {JSON.stringify(item, null, 2)}
          </pre>
        </details>
      ))}
      <form
        className="form-stack"
        style={{ marginTop: 18 }}
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const data = JSON.parse(
              String(new FormData(e.currentTarget).get("record")),
            );
            key.current ||= crypto.randomUUID();
            await command(`/admin/${kind}`, data, key.current);
            key.current = "";
            await result.reload();
          } catch (e) {
            setError(e as Error);
          }
        }}
      >
        <label>
          New {kind === "templates" ? "immutable template version" : "issue"}{" "}
          (backend schema JSON)
          <textarea name="record" required rows={8} />
        </label>
        <button className="button secondary">
          Create {kind === "templates" ? "template version" : "issue"}
        </button>
      </form>
    </section>
  );
}
export function AuditTrail() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState("");
  const result = useResource<
    Page<{
      id: string;
      event_type: string;
      actor_name?: string;
      created_at: string;
      summary: string;
    }>
  >(`/admin/audit-events?${new URLSearchParams({ search, cursor })}`);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACCOUNTABLE BY DESIGN</div>
          <h1>The editorial record.</h1>
          <p>
            Search redacted events across access, reviews, payment decisions,
            and publication.
          </p>
        </div>
      </div>
      <form
        className="actions"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(query);
          setCursor("");
        }}
      >
        <label>
          Search events
          <input value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <button className="button">Search</button>
      </form>
      <ErrorNotice error={result.error} retry={result.reload} />
      <section className="panel" style={{ marginTop: 25 }}>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>EVENT</th>
                <th>ACTOR</th>
                <th>DATE</th>
                <th>SUMMARY</th>
              </tr>
            </thead>
            <tbody>
              {result.data?.items.map((event) => (
                <tr key={event.id}>
                  <td>{event.event_type}</td>
                  <td>{event.actor_name || "System"}</td>
                  <td>{date(event.created_at)}</td>
                  <td>{event.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {result.data?.items.length === 0 && (
          <Empty title="No events found">Try a different search.</Empty>
        )}
      </section>
      <div className="actions">
        {cursor && (
          <button className="text-link" onClick={() => setCursor("")}>
            First page
          </button>
        )}
        {result.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(result.data!.next_cursor!)}
          >
            Next →
          </button>
        )}
      </div>
    </>
  );
}
