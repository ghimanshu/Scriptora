"use client";
import { useState, useRef } from "react";
import { useResource, ErrorNotice, Loading } from "@/components/common/data";
import { FileUpload } from "@/components/forms/file-upload";
import { command } from "@/lib/api-client";
import { money } from "@/lib/formatting";
import type { Invoice, PaymentAttempt, Page } from "@/types/api";
export function Payment({
  articleId,
  admin = false,
}: {
  articleId: string;
  admin?: boolean;
}) {
  const invoice = useResource<Invoice>(`/articles/${articleId}/invoice`);
  const attempts = useResource<Page<PaymentAttempt>>(
    invoice.data ? `/invoices/${invoice.data.id}/payment-attempts` : null,
  );
  const [proof, setProof] = useState("");
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const key = useRef("");
  const i = invoice.data;
  const pending = attempts.data?.items.some((a) => a.status === "SUBMITTED");
  return (
    <section className="panel">
      <h2>Publication payment</h2>
      <ErrorNotice
        error={invoice.error || attempts.error || error}
        retry={() => {
          void invoice.reload();
          void attempts.reload();
        }}
      />
      {invoice.loading && <Loading />}
      {i && (
        <>
          <div className="page-heading">
            <strong style={{ fontSize: 28 }}>
              {money(i.amount_minor, i.currency)}
            </strong>
            <span className="badge">{i.status}</span>
          </div>
          <p>{i.instructions}</p>
          <p className="subtle">
            Your fee and payment instructions are fixed for the approved
            manuscript version. Proof submission does not verify payment or
            publish your article.
          </p>
          {attempts.data?.items.map((attempt) => (
            <div className="feedback" key={attempt.id}>
              <strong>
                {attempt.status} · {attempt.reference}
              </strong>
              <p>{attempt.reason}</p>
              <a
                className="file-link"
                href={`/api/v1/files/${attempt.proof_file_id}/download`}
              >
                View proof ↓
              </a>
              {admin && attempt.status === "SUBMITTED" && (
                <PaymentDecision
                  attempt={attempt}
                  onDone={() => {
                    void attempts.reload();
                    void invoice.reload();
                  }}
                />
              )}
            </div>
          ))}
          {!admin && i.status === "OPEN" && attempts.data && !pending && (
            <form
              className="form-stack"
              style={{ marginTop: 22 }}
              onSubmit={async (e) => {
                e.preventDefault();
                setError(undefined);
                setBusy(true);
                const data = new FormData(e.currentTarget);
                try {
                  if (!proof)
                    throw new Error("Upload your payment proof first.");
                  key.current ||= crypto.randomUUID();
                  await command(
                    `/invoices/${i.id}/payment-attempts`,
                    {
                      reference: data.get("reference"),
                      payment_date: data.get("payment_date"),
                      amount_minor: i.amount_minor,
                      currency: i.currency,
                      proof_file_id: proof,
                    },
                    key.current,
                  );
                  await attempts.reload();
                } catch (e) {
                  setError(e as Error);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label>
                Transaction reference / UTR
                <input name="reference" required maxLength={120} />
              </label>
              <label>
                Payment date
                <input name="payment_date" type="date" required />
              </label>
              <label>
                Amount
                <input value={money(i.amount_minor, i.currency)} readOnly />
              </label>
              <FileUpload
                articleId={articleId}
                kind="payment_proof"
                onUploaded={(f) => setProof(f.id)}
              />
              <button className="button" disabled={busy}>
                Submit payment proof
              </button>
            </form>
          )}
          {pending && (
            <div className="notice success" role="status">
              Proof received. An administrator will verify the actual receipt.
            </div>
          )}
        </>
      )}
    </section>
  );
}
export function PaymentDecision({
  attempt,
  onDone,
}: {
  attempt: PaymentAttempt;
  onDone: () => void;
}) {
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState("verify");
  const [confirmed, setConfirmed] = useState(false);
  const key = useRef("");
  return (
    <form
      className="form-stack"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!confirmed) return;
        const data = new FormData(e.currentTarget);
        setBusy(true);
        setError(undefined);
        try {
          key.current ||= crypto.randomUUID();
          await command(
            `/admin/payment-attempts/${attempt.id}/${decision}`,
            decision === "verify"
              ? {
                  verified_reference: data.get("reference"),
                  receipt_note: data.get("reason"),
                }
              : { reason: data.get("reason") },
            key.current,
          );
          onDone();
        } catch (e) {
          setError(e as Error);
        } finally {
          setBusy(false);
        }
      }}
    >
      <ErrorNotice error={error} />
      <label>
        Decision
        <select
          value={decision}
          onChange={(e) => {
            setDecision(e.target.value);
            key.current = "";
            setConfirmed(false);
          }}
        >
          <option value="verify">Verify receipt</option>
          <option value="reject">Reject proof</option>
        </select>
      </label>
      {decision === "verify" && (
        <label>
          Verified bank reference
          <input name="reference" defaultValue={attempt.reference} required />
        </label>
      )}
      <label>
        {decision === "verify" ? "Reconciliation note" : "Rejection reason"}
        <textarea name="reason" required />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          required
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        {decision === "verify"
          ? "I checked the actual receipt, beneficiary, amount, and reference against bank records."
          : "I confirm this rejection and its reason."}
      </label>
      <button className="button" disabled={busy || !confirmed}>
        Confirm {decision === "verify" ? "verification" : "rejection"}
      </button>
    </form>
  );
}
