"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, command } from "@/lib/api-client";
import { useResource, ErrorNotice } from "@/components/common/data";
import { FileUpload } from "./file-upload";
import type { Article, Taxon } from "@/types/api";
export function SubmissionWizard() {
  const subjects = useResource<Taxon[]>("/subjects");
  const types = useResource<Taxon[]>("/publication-types");
  const outlets = useResource<Taxon[]>("/outlets");
  const [step, setStep] = useState(0);
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Article>();
  const [fileId, setFileId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [fields, setFields] = useState({
    publication_type_id: "",
    outlet_id: "",
    primary_subject_id: "",
    title: "",
    abstract: "",
    keywords: "",
    author_name: "",
    author_email: "",
    affiliation: "",
    originality: false,
    copyright: false,
    conflicts: false,
  });
  const [authors, setAuthors] = useState<
    { name: string; email: string; affiliation: string }[]
  >([]);
  const form = useRef<HTMLFormElement>(null);
  const router = useRouter();
  const submitKey = useRef<string>("");
  const saveAttempt = useRef<{ signature: string; key: string } | null>(null);
  const templateId = outlets.data?.find(
    (outlet) => outlet.id === fields.outlet_id,
  )?.template_id;
  const template = useResource<Record<string, unknown>>(
    templateId ? `/templates/${templateId}` : null,
  );
  const update = (key: keyof typeof fields, value: string | boolean) =>
    setFields((previous) => ({ ...previous, [key]: value }));
  async function save() {
    if (!templateId) {
      throw new Error("Choose an outlet with an active submission template.");
    }
    const primaryAuthor = {
      name: fields.author_name.trim(),
      email: fields.author_email.trim(),
      affiliation: fields.affiliation.trim(),
    };
    const metadata = {
      title: fields.title,
      abstract: fields.abstract,
      keywords: fields.keywords.split(",").map((s) => s.trim()).filter(Boolean),
      authors: primaryAuthor.name && primaryAuthor.email && primaryAuthor.affiliation
        ? [primaryAuthor, ...authors] : [],
      declarations: {
        originality: fields.originality,
        copyright: fields.copyright,
        conflict: fields.conflicts,
      },
    };
    const payload = draft
      ? { metadata, manuscript_file_id: fileId || null }
      : {
          primary_subject_id: fields.primary_subject_id,
          outlet_id: fields.outlet_id,
          template_id: templateId,
          metadata,
          manuscript_file_id: fileId || null,
        };
    const path = draft ? `/articles/${draft.id}` : "/articles";
    const method = draft ? "PATCH" : "POST";
    const body = JSON.stringify(payload);
    const signature = JSON.stringify([path, method, draft?.lock_version, body]);
    if (saveAttempt.current?.signature !== signature) {
      saveAttempt.current = { signature, key: crypto.randomUUID() };
    }
    const headers: Record<string, string> = {
      "Idempotency-Key": saveAttempt.current.key,
    };
    if (draft) headers["If-Match"] = String(draft.lock_version);
    const result = await api<Article>(path, { method, headers, body });
    saveAttempt.current = null;
    setDraft(result);
    return result;
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR NEXT CHAPTER</div>
          <h1>Make room for your ideas.</h1>
          <p>A few considered steps to prepare your manuscript for review.</p>
        </div>
        <Link className="text-link" href="/author/articles">
          ← My articles
        </Link>
      </div>
      <section className="panel form-panel">
        <div className="stepper" aria-label="Submission progress">
          {["Publication", "Manuscript", "Declarations", "Review & submit"].map(
            (label, i) => (
              <span
                key={label}
                className={step === i ? "current" : ""}
                aria-current={step === i ? "step" : undefined}
              >
                {i + 1}. {label}
              </span>
            ),
          )}
        </div>
        <ErrorNotice
          error={
            error ||
            subjects.error ||
            types.error ||
            outlets.error ||
            template.error
          }
          retry={() => {
            void subjects.reload();
            void types.reload();
            void outlets.reload();
          }}
        />
        <form
          ref={form}
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(undefined);
            try {
              if (step === 0) {
                await save();
                setStep(1);
              } else if (step < 3) {
                await save();
                setStep(step + 1);
              } else {
                if (!confirmed || !fileId)
                  throw new Error(
                    "Attach your manuscript and confirm the submission.",
                  );
                const article = await save();
                submitKey.current ||= crypto.randomUUID();
                await command(
                  `/articles/${article.id}/submit`,
                  { expected_version: article.lock_version },
                  submitKey.current,
                );
                router.push(`/author/articles/${article.id}`);
              }
            } catch (e) {
              setError(e as Error);
            } finally {
              setBusy(false);
            }
          }}
        >
          {step === 0 && (
            <fieldset className="form-section">
              <legend>Find the right home for your work</legend>
              <p>
                Select your publication and subject. These determine the
                submission template and reviewer expertise.
              </p>
              <div className="form-grid">
                {[
                  ["publication_type_id", "Publication type", types.data],
                  ["outlet_id", "Publication outlet", outlets.data?.filter((outlet) => outlet.type_id === fields.publication_type_id)],
                  ["primary_subject_id", "Primary subject", subjects.data],
                ].map(([key, label, data]) => (
                  <label key={String(key)}>
                    {String(label)}
                    <select
                      disabled={Boolean(draft)}
                      required
                      value={String(fields[key as keyof typeof fields])}
                      onChange={(e) => {
                        update(key as keyof typeof fields, e.target.value);
                        if (key === "publication_type_id") update("outlet_id", "");
                      }}
                    >
                      <option value="">Choose an option</option>
                      {(data as Taxon[] | undefined)?.map((t) => (
                        <option value={t.id} key={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              {template.data && (
                <details style={{ marginTop: 20 }}>
                  <summary>Submission template requirements</summary>
                  <pre style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                    {JSON.stringify(template.data, null, 2)}
                  </pre>
                </details>
              )}
            </fieldset>
          )}
          {step === 1 && (
            <fieldset className="form-section">
              <legend>Give your manuscript a clear introduction</legend>
              <div className="form-grid">
                <label className="full">
                  Article title
                  <input
                    required
                    maxLength={500}
                    value={fields.title}
                    onChange={(e) => update("title", e.target.value)}
                    placeholder="A title that captures your contribution"
                  />
                </label>
                <label className="full">
                  Abstract
                  <textarea
                    required
                    value={fields.abstract}
                    onChange={(e) => update("abstract", e.target.value)}
                  />
                </label>
                <label className="full">
                  Keywords
                  <input
                    required
                    value={fields.keywords}
                    onChange={(e) => update("keywords", e.target.value)}
                    placeholder="Separate keywords with commas"
                  />
                </label>
                <label>
                  Corresponding author
                  <input
                    required
                    value={fields.author_name}
                    onChange={(e) => update("author_name", e.target.value)}
                  />
                </label>
                <label>
                  Author email
                  <input
                    type="email"
                    required
                    value={fields.author_email}
                    onChange={(e) => update("author_email", e.target.value)}
                  />
                </label>
                <label className="full">
                  Affiliation
                  <input
                    required
                    value={fields.affiliation}
                    onChange={(e) => update("affiliation", e.target.value)}
                  />
                </label>
                <div className="full form-stack">
                  <h3>Coauthors, in publication order</h3>
                  {authors.map((a, i) => (
                    <div className="coauthor-row" key={i}>
                      {["name", "email", "affiliation"].map((k) => (
                        <label key={k}>
                          {k}
                          <input
                            type={k === "email" ? "email" : "text"}
                            required
                            value={a[k as keyof typeof a]}
                            onChange={(e) =>
                              setAuthors((previous) =>
                                previous.map((item, index) =>
                                  index === i
                                    ? { ...item, [k]: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                        </label>
                      ))}
                      <button
                        type="button"
                        className="text-link"
                        onClick={() =>
                          setAuthors((previous) =>
                            previous.filter((_, index) => index !== i),
                          )
                        }
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="button secondary small"
                    onClick={() =>
                      setAuthors((previous) => [
                        ...previous,
                        { name: "", email: "", affiliation: "" },
                      ])
                    }
                  >
                    + Add coauthor
                  </button>
                  {draft && (
                    <FileUpload
                      articleId={draft.id}
                      onUploaded={(file) => setFileId(file.id)}
                    />
                  )}
                </div>
              </div>
            </fieldset>
          )}
          {step === 2 && (
            <fieldset className="form-section">
              <legend>A shared commitment to good publishing</legend>
              <p>
                Confirm the following declarations for this manuscript version.
              </p>
              <div className="form-stack">
                {[
                  [
                    "originality",
                    "This work is original and is not under review elsewhere.",
                  ],
                  [
                    "copyright",
                    "All authors consent to submission and have the right to publish this content.",
                  ],
                  [
                    "conflicts",
                    "All competing interests have been disclosed in the manuscript.",
                  ],
                ].map(([key, label]) => (
                  <label className="checkbox" key={key}>
                    <input
                      type="checkbox"
                      required
                      checked={Boolean(fields[key as keyof typeof fields])}
                      onChange={(e) =>
                        update(key as keyof typeof fields, e.target.checked)
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {step === 3 && (
            <fieldset className="form-section">
              <legend>Ready for a fresh perspective?</legend>
              <p>
                Submission freezes this manuscript version. The backend
                validates the outlet template, required metadata, declarations,
                and file scan before accepting it.
              </p>
              <h2>{fields.title}</h2>
              <p>{fields.abstract}</p>
              <p>
                {fields.author_name}
                {authors.length
                  ? ` and ${authors.length} coauthor(s)`
                  : ""} · {fields.affiliation}
              </p>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={confirmed}
                  required
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I have reviewed this manuscript and confirm that it is ready for
                expert review.
              </label>
            </fieldset>
          )}
          <div className="form-actions">
            <button
              className="button secondary"
              type="button"
              disabled={busy}
              onClick={() =>
                step > 0 ? setStep(step - 1) : router.push("/author/articles")
              }
            >
              {step ? "← Back" : "Cancel"}
            </button>
            <button className="button" disabled={busy}>
              {busy
                ? "Saving…"
                : step === 3
                  ? "Confirm & submit manuscript"
                  : "Save & continue →"}
            </button>
          </div>
          {draft && (
            <p className="subtle" style={{ marginTop: 14 }}>
              Draft saved ·{" "}
              <a href={`/author/articles/${draft.id}`}>Open saved draft ↗</a>
            </p>
          )}
        </form>
      </section>
    </>
  );
}
