"use client";
import { useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ErrorNotice } from "@/components/common/data";
import { command } from "@/lib/api-client";

export function DeleteArticle({ articleId, title = "this draft", onDeleted }: {
  articleId: string; title?: string; onDeleted?: () => void;
}) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  const descriptionId = useId();
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<Error>();
  const request = useRef({ reason: "", key: "" });
  return <>
    <button type="button" className="button danger small" disabled={busy}
      aria-label={`Delete ${title}`} onClick={() => {
        setError(undefined);
        dialog.current?.showModal();
      }}>Delete</button>
    <dialog ref={dialog} className="confirmation-dialog" aria-labelledby={headingId}
      aria-describedby={descriptionId} onCancel={event => { if (busy) event.preventDefault(); }}>
      <h2 id={headingId}>Delete this draft?</h2>
      <p id={descriptionId}>Deleting <strong>{title}</strong> removes it from My Articles. You will no longer be able to open or edit this draft. Only drafts can be deleted.</p>
      <form className="form-stack" onSubmit={async event => {
        event.preventDefault();
        if (busy) return;
        const value = reason.trim() || "Draft removed by its author.";
        if (value.length < 3) { setError(new Error("Enter at least three characters for the reason, or leave it blank.")); return; }
        if (request.current.reason !== value || !request.current.key)
          request.current = { reason: value, key: crypto.randomUUID() };
        setBusy(true);
        setError(undefined);
        try {
          await command(`/articles/${articleId}`, { reason: value }, request.current.key, "DELETE");
          dialog.current?.close();
          if (onDeleted) onDeleted();
          else { router.replace("/author/articles"); router.refresh(); }
        } catch (cause) { setError(cause as Error); setBusy(false); }
      }}>
        <label>Reason for deletion (optional)
          <textarea value={reason} onChange={event => setReason(event.target.value)} minLength={3}
            maxLength={2000} rows={3} disabled={busy} />
        </label>
        <ErrorNotice error={error} />
        <div className="actions confirmation-actions">
          <button type="button" className="button secondary" disabled={busy} onClick={() => dialog.current?.close()}>Cancel</button>
          <button type="submit" className="button danger" disabled={busy}>{busy ? "Deleting..." : "Delete draft"}</button>
        </div>
      </form>
    </dialog>
  </>;
}
