"use client";
import Link from "next/link";
import { useState } from "react";
import {
  useResource,
  ErrorNotice,
  Empty,
  Loading,
} from "@/components/common/data";
import { Icon } from "@/components/common/icon";
import { date } from "@/lib/formatting";
import type { Article, Page, Taxon } from "@/types/api";
export function Catalog() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [subject, setSubject] = useState("");
  const [outlet, setOutlet] = useState("");
  const [cursor, setCursor] = useState("");
  const subjects = useResource<Taxon[]>("/subjects");
  const outlets = useResource<Taxon[]>("/outlets");
  const params = new URLSearchParams({
    search,
    subject_id: subject,
    outlet_id: outlet,
    ...(cursor ? { cursor } : {}),
  });
  const result = useResource<Page<Article>>(`/public/articles?${params}`);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">THE SCRIPTORA LIBRARY</div>
          <h1>Ideas, out in the world.</h1>
          <p>Explore our published articles, journals, and newsletters.</p>
        </div>
      </div>
      <form
        className="actions"
        onSubmit={(e) => {
          e.preventDefault();
          setCursor("");
          setSearch(query);
        }}
      >
        <label className="search-box">
          <Icon name="search" size={17} />
          <input
            placeholder="Search publications…"
            aria-label="Search publications"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          aria-label="Subject"
          value={subject}
          onChange={(e) => {
            setCursor("");
            setSubject(e.target.value);
          }}
        >
          <option value="">All subjects</option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Outlet"
          value={outlet}
          onChange={(e) => {
            setCursor("");
            setOutlet(e.target.value);
          }}
        >
          <option value="">All outlets</option>
          {outlets.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button className="button">Search</button>
      </form>
      <ErrorNotice
        error={subjects.error || outlets.error}
        retry={() => {
          void subjects.reload();
          void outlets.reload();
        }}
      />
      <ErrorNotice error={result.error} retry={result.reload} />
      {result.loading ? (
        <Loading />
      ) : (
        result.data &&
        (result.data.items.length ? (
          <div className="public-grid" style={{ marginTop: 30 }}>
            {result.data.items.map((article) => (
              <article className="article-card" key={article.id}>
                <span className="eyebrow">
                  {article.subject || "PUBLICATION"}
                </span>
                <h2>
                  <Link href={`/articles/${article.slug}`}>
                    {article.title}
                  </Link>
                </h2>
                <p>{article.abstract?.slice(0, 180)}</p>
                <small className="subtle">
                  {article.author_names?.join(", ")} ·{" "}
                  {date(article.published_at)}
                </small>
                <Link className="text-link" href={`/articles/${article.slug}`}>
                  Read article ↗
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="No publications found">
            Try another subject or search term.
          </Empty>
        ))
      )}
      <div className="actions" style={{ marginTop: 25 }}>
        {cursor && (
          <button className="button secondary" onClick={() => setCursor("")}>
            First page
          </button>
        )}
        {result.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(result.data!.next_cursor!)}
          >
            More publications →
          </button>
        )}
      </div>
    </>
  );
}
export function PublicArticle({ slug }: { slug: string }) {
  const result = useResource<Article>(
    `/public/articles/${encodeURIComponent(slug)}`,
  );
  return (
    <>
      <Link href="/articles" className="text-link">
        ← Back to the library
      </Link>
      <ErrorNotice error={result.error} retry={result.reload} />
      {result.loading ? (
        <Loading />
      ) : (
        result.data && (
          <article style={{ maxWidth: 800, margin: "45px auto" }}>
            <div className="eyebrow">
              {result.data.subject} · {result.data.outlet}
            </div>
            <h1>{result.data.title}</h1>
            <p className="subtle" style={{ margin: "20px 0" }}>
              {result.data.author_names?.join(", ")} · Published{" "}
              {date(result.data.published_at)}
            </p>
            <section className="panel form-panel">
              <h2>Abstract</h2>
              <p style={{ margin: "20px 0", whiteSpace: "pre-wrap" }}>
                {result.data.abstract}
              </p>
              <a
                href={`/api/v1/public/articles/${encodeURIComponent(slug)}/file`}
                className="button"
              >
                Download published article ↓
              </a>
            </section>
          </article>
        )
      )}
    </>
  );
}
