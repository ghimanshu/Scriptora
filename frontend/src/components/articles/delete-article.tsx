"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ErrorNotice } from "@/components/common/data";
import { command } from "@/lib/api-client";

export function DeleteArticle({ articleId }: { articleId: string }) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const request = useRef({ reason: "", key: "" });
  return (
    <section className="panel">
      <h2>Delete article</h2>
      <p>The article will be removed from access, including public listings. The author will receive an email with your reason.</p>
      <ErrorNotice error={error} />
      <form className="form-stack" onSubmit={async (event) => {
        event.preventDefault();
        const value = reason.trim();
        if (busy || value.length < 3) return;
        if (request.current.reason !== value || !request.current.key)
          request.current = { reason: value, key: crypto.randomUUID() };
        setBusy(true);
        setError(undefined);
        try {
          await command(`/admin/articles/${articleId}`, { reason: value }, request.current.key, "DELETE");
          router.replace("/admin/articles");
          router.refresh();
        } catch (cause) {
          setError(cause as Error);
          setBusy(false);
        }
      }}>
        <label>
          Reason for deletion
          <textarea required minLength={3} maxLength={2000} rows={4} value={reason}
            disabled={busy} onChange={(event) => setReason(event.target.value)} />
        </label>
        <button className="button" disabled={busy || reason.trim().length < 3}>
          {busy ? "Deleting article..." : "Delete article and notify author"}
        </button>
      </form>
    </section>
  );
}
