"use client";
import { useState, useRef } from "react";
import { command } from "@/lib/api-client";
import { ErrorNotice } from "@/components/common/data";
import type { Article } from "@/types/api";
export function PublicationForm({
  article,
  onDone,
}: {
  article: Article;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const key = useRef("");
  return (
    <section className="panel">
      <h2>Publish the approved version</h2>
      <p>
        Publication requires verified full payment and the approved final
        artifact. Confirm any issue or volume requirements from the outlet
        template.
      </p>
      <ErrorNotice error={error} />
      <form
        className="form-stack"
        style={{ marginTop: 20 }}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          const fields = new FormData(e.currentTarget);
          try {
            key.current ||= crypto.randomUUID();
            await command(
              `/admin/articles/${article.id}/publish`,
              {
                approved_version_id: article.approved_version_id,
                final_file_id: fields.get("final_file_id"),
                expected_version: article.lock_version,
                publication: {
                  title: fields.get("title"),
                  slug: fields.get("slug"),
                  public_authors: String(fields.get("authors"))
                    .split(",")
                    .map((s) => s.trim()),
                  issue_id: fields.get("issue_id") || undefined,
                  published_at: new Date().toISOString(),
                },
              },
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
        <label>
          Public title
          <input name="title" defaultValue={article.title} required />
        </label>
        <label>
          Stable URL slug
          <input
            name="slug"
            required
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            placeholder="your-article-title"
          />
        </label>
        <label>
          Public author names (comma separated)
          <input
            name="authors"
            required
            defaultValue={article.author_names?.join(", ")}
          />
        </label>
        <label>
          Approved final artifact ID
          <input name="final_file_id" required />
        </label>
        <label>
          Journal issue ID, if required
          <input name="issue_id" />
        </label>
        <label className="checkbox">
          <input type="checkbox" required />I confirm the payment is verified
          and this is the approved manuscript and publication metadata.
        </label>
        <button className="button" disabled={busy}>
          Confirm & publish article
        </button>
      </form>
    </section>
  );
}
