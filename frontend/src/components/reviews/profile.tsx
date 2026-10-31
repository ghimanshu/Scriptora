"use client";
import { useState } from "react";
import { useResource, ErrorNotice } from "@/components/common/data";
import { api } from "@/lib/api-client";
import type { Taxon } from "@/types/api";
export function ReviewerProfile() {
  const all = useResource<Taxon[]>("/subjects");
  const mine = useResource<string[]>("/reviewers/me/subjects");
  const [error, setError] = useState<Error>();
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">REVIEWER PROFILE</div>
          <h1>Your expertise makes a difference.</h1>
          <p>Choose the subjects you can confidently review.</p>
        </div>
      </div>
      <section className="panel form-panel">
        <ErrorNotice
          error={error || all.error || mine.error}
          retry={() => {
            void all.reload();
            void mine.reload();
          }}
        />
        {saved && (
          <div className="notice success" role="status">
            {saved}
          </div>
        )}
        {all.data && mine.data && (
          <form
            key={JSON.stringify(mine.data)}
            className="form-stack"
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              setBusy(true);
              try {
                await api("/reviewers/me/subjects", {
                  method: "PUT",
                  body: JSON.stringify({
                    subject_ids: data.getAll("subjects"),
                  }),
                });
                setSaved("Expertise subscriptions updated.");
                await mine.reload();
              } catch (e) {
                setError(e as Error);
              } finally {
                setBusy(false);
              }
            }}
          >
            <h2>Subject subscriptions</h2>
            {all.data.map((subject) => (
              <label className="checkbox" key={subject.id}>
                <input
                  type="checkbox"
                  name="subjects"
                  value={subject.id}
                  defaultChecked={mine.data!.includes(subject.id)}
                />
                {subject.name}
              </label>
            ))}
            <button className="button" disabled={busy}>
              Save expertise
            </button>
          </form>
        )}
        <form
          className="form-stack"
          style={{ marginTop: 35 }}
          onSubmit={async (e) => {
            e.preventDefault();
            const available =
              new FormData(e.currentTarget).get("available") === "true";
            setBusy(true);
            try {
              await api("/reviewers/me/availability", {
                method: "PATCH",
                body: JSON.stringify({ available }),
              });
              setSaved(
                "Availability updated. Existing assignments retain their deadlines.",
              );
            } catch (e) {
              setError(e as Error);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2>Availability</h2>
          <label>
            Accept new assignments
            <select name="available">
              <option value="true">Available</option>
              <option value="false">Unavailable</option>
            </select>
          </label>
          <p className="subtle">
            Going unavailable does not abandon existing assignments.
          </p>
          <button className="button secondary" disabled={busy}>
            Update availability
          </button>
        </form>
      </section>
    </>
  );
}
