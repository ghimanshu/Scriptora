"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useResource, ErrorNotice, Empty, Loading } from "./data";
import { api, command } from "@/lib/api-client";
import { PaymentDecision } from "@/components/payments/payment";
import { money, date } from "@/lib/formatting";
import type { Page, PaymentAttempt, User, Taxon } from "@/types/api";
export function AdminPayments() {
  const [cursor, setCursor] = useState("");
  const result = useResource<Page<PaymentAttempt>>(
    `/admin/payments?${new URLSearchParams({ cursor })}`,
  );
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
      ) : result.data?.items.length === 0 ? (
        <section className="panel">
          <Empty title="All caught up">
            Payment proofs awaiting verification will appear here.
          </Empty>
        </section>
      ) : (
        result.data?.items.map((attempt) => (
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
            Next page →
          </button>
        )}
      </div>
    </>
  );
}
export function AdminPeople() {
  const [cursor, setCursor] = useState("");
  const users = useResource<Page<User & { active: boolean }>>(
    `/admin/users?${new URLSearchParams({ cursor })}`,
  );
  const reviewers = useResource<Page<User>>("/admin/reviewers");
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
          {reviewers.data?.items.map((user) => (
            <div className="assignment-row" key={user.id}>
              <div>
                <strong>{user.name}</strong>
                <p>{user.email}</p>
              </div>
              <button
                className="button secondary small"
                disabled={busy}
                onClick={async () => {
                  const reason = window.prompt(
                    `Reason for approving ${user.name} as reviewer:`,
                  );
                  if (!reason) return;
                  setBusy(true);
                  try {
                    await command(`/admin/reviewers/${user.id}/approve`, {
                      reason,
                    });
                    setMessage("Reviewer approval recorded.");
                    await reviewers.reload();
                  } catch (e) {
                    setError(e as Error);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Approve
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
                  <td>{user.roles.join(", ")}</td>
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
      <div className="settings-grid">
        <SettingsEditor />
        <Taxonomy kind="subjects" />
        <Taxonomy kind="outlets" />
        <RecordEditor kind="templates" title="Versioned templates" />
        <RecordEditor kind="issues" title="Journal issues" />
      </div>
    </>
  );
}
function SettingsEditor() {
  const resource = useResource<{
    lock_version: number;
    schema_version: number;
    [key: string]: unknown;
  }>("/admin/settings");
  const [error, setError] = useState<Error>();
  const [saved, setSaved] = useState(false);
  return (
    <section className="panel">
      <h2>Workflow settings</h2>
      <ErrorNotice error={error || resource.error} retry={resource.reload} />
      {saved && (
        <p role="status" className="subtle">
          Settings saved.
        </p>
      )}
      {resource.data && (
        <form
          key={JSON.stringify(resource.data)}
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              const payload = JSON.parse(
                String(new FormData(e.currentTarget).get("settings")),
              );
              await api("/admin/settings", {
                method: "PUT",
                headers: { "If-Match": String(resource.data!.lock_version) },
                body: JSON.stringify(payload),
              });
              setSaved(true);
              await resource.reload();
            } catch (e) {
              setError(e as Error);
            }
          }}
        >
          <label>
            Schema-versioned configuration
            <textarea
              name="settings"
              rows={12}
              required
              defaultValue={JSON.stringify(resource.data, null, 2)}
            />
            <small>
              Use the backend configuration schema. No database credentials or
              secrets.
            </small>
          </label>
          <button className="button">Save settings</button>
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
