"use client";
import { useState } from "react";
import { api } from "@/lib/api-client";
import { manuscript } from "@/lib/validation";
import { ErrorNotice } from "@/components/common/data";
import { Icon } from "@/components/common/icon";
import type { Upload } from "@/types/api";
export function FileUpload({
  articleId,
  kind = "manuscript",
  onUploaded,
}: {
  articleId: string;
  kind?: string;
  onUploaded: (file: Upload) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<Upload>();
  const [error, setError] = useState<Error>();
  return (
    <div className="upload-box">
      <Icon name="upload" />
      <label>
        {kind === "payment_proof" ? "Payment proof" : "Manuscript file"}
        <input
          type="file"
          disabled={busy}
          accept={
            kind === "payment_proof" ? ".pdf,.png,.jpg,.jpeg" : ".pdf,.docx"
          }
          onChange={async (e) => {
            const selected = e.target.files?.[0];
            if (!selected) return;
            setError(undefined);
            const issue = manuscript(selected, kind);
            if (issue) {
              setError(new Error(issue));
              return;
            }
            setBusy(true);
            try {
              const data = new FormData();
              data.append("kind", kind);
              data.append("article_id", articleId);
              data.append("file", selected);
              const upload = await api<Upload>("/files", {
                method: "POST",
                body: data,
              });
              setFile(upload);
              onUploaded(upload);
            } catch (e) {
              setError(e as Error);
            } finally {
              setBusy(false);
            }
          }}
        />
      </label>
      <p>
        {busy
          ? "Uploading securely…"
          : file
            ? `File received · scan status: ${file.scan_status}. Submission is allowed only after the backend confirms a clean file.`
            : kind === "payment_proof"
              ? "PNG, JPEG, or PDF · up to 10 MiB"
              : "PDF or DOCX · up to 20 MiB. Files are scanned before use."}
      </p>
      <ErrorNotice error={error} />
    </div>
  );
}
