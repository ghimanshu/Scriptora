"use client";
import Link from "next/link";
import { useState } from "react";
import { ArticleTable } from "@/components/articles/article-table";
import { useResource, ErrorNotice, Loading, Empty } from "./data";
import { Icon } from "./icon";
import type { Area } from "./shell";
import type { Article, Page, Assignment } from "@/types/api";
import { deadline } from "@/lib/formatting";
export function Dashboard({
  area,
  list = false,
}: {
  area: Area;
  list?: boolean;
}) {
  const path =
    area === "admin"
      ? "/admin/articles"
      : area === "reviewer"
        ? "/assignments/me"
        : "/articles";
  const resource = useResource<Page<Article & Assignment>>(path);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const more = useResource<Page<Article & Assignment>>(
    cursor ? `${path}?cursor=${encodeURIComponent(cursor)}` : null,
  );
  const page = cursor ? more : resource;
  const items = page.data?.items || [];
  const title =
    area === "author"
      ? list
        ? "My articles"
        : "Your ideas. Their next chapter."
      : area === "reviewer"
        ? list
          ? "My assignments"
          : "A fresh perspective starts with you."
        : list
          ? "All articles"
          : "A clear view of your publication.";
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {area === "author"
              ? "AUTHOR"
              : area === "reviewer"
                ? "REVIEWER"
                : "EDITORIAL"}{" "}
            WORKSPACE
          </div>
          <h1>{title}</h1>
          <p>
            {area === "author"
              ? "Manage your manuscripts, follow reviews, and bring your work to the world."
              : area === "reviewer"
                ? "Give promising work the thoughtful review it deserves."
                : "Keep submissions moving and every publishing decision accountable."}
          </p>
        </div>
        <Link
          className="button"
          href={
            area === "author"
              ? "/author/articles/new"
              : area === "reviewer"
                ? "/reviewer/queue"
                : "/admin/payments"
          }
        >
          <Icon name={area === "author" ? "plus" : "arrow"} size={18} />
          {area === "author"
            ? "New submission"
            : area === "reviewer"
              ? "Browse review queue"
              : "Review payments"}
        </Link>
      </div>
      {!list && (
        <>
          <div className="stats-grid">
            {(area === "reviewer"
              ? [
                  ["Assignments on this page", items.length, "article"],
                  [
                    "Active reviews",
                    items.filter((a) => a.state === "ACTIVE").length,
                    "clock",
                  ],
                  [
                    "Reserved revisions",
                    items.filter((a) => a.state === "RESERVED").length,
                    "book",
                  ],
                  [
                    "Completed",
                    items.filter((a) => a.state === "COMPLETED").length,
                    "check",
                  ],
                ]
              : [
                  ["Articles on this page", items.length, "article"],
                  [
                    "In review",
                    items.filter((a) => a.status === "IN_REVIEW").length,
                    "clock",
                  ],
                  [
                    "Changes requested",
                    items.filter((a) => a.status === "REVIEWED").length,
                    "book",
                  ],
                  [
                    "Published",
                    items.filter((a) => a.status === "PUBLISH").length,
                    "check",
                  ],
                ]
            ).map(([label, count, icon], i) => (
              <div className="stat-card" key={label}>
                <span className={`stat-icon tone-${i}`}>
                  <Icon name={String(icon)} />
                </span>
                <span className="stat-label">{label}</span>
                <strong>{page.data ? count : "—"}</strong>
                <small>
                  {i === 0
                    ? "Current page · up to 25 records"
                    : "Within this page"}
                </small>
              </div>
            ))}
          </div>
          <div className="welcome-banner">
            <div>
              <span className="eyebrow">
                FROM MANUSCRIPT TO MEANINGFUL IMPACT
              </span>
              <h2>Good research deserves to be read.</h2>
              <p>
                A considered process. Expert perspectives. A place for your
                voice.
              </p>
              <Link
                href={area === "author" ? "/author/articles/new" : "/articles"}
              >
                {area === "author"
                  ? "Begin your next submission"
                  : "Explore the published library"}{" "}
                <span>→</span>
              </Link>
            </div>
            <div className="book-illustration" aria-hidden="true">
              <div className="book-back" />
              <div className="book-front">
                <span>SCRIPTORA</span>
                <div className="book-lines" />
                <strong>
                  Ideas
                  <br />
                  into
                  <br />
                  <em>impact.</em>
                </strong>
                <span>THE NEXT CHAPTER</span>
              </div>
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <span className="spark">✳</span>
            </div>
          </div>
        </>
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>{area === "reviewer" ? "Your assignments" : "Manuscripts"}</h2>
            <p>
              {area === "reviewer"
                ? "Exact deadlines are set by the publishing service."
                : "Every draft, review, and milestone in one place."}
            </p>
          </div>
          <button className="text-link" onClick={() => void page.reload()}>
            Refresh ↻
          </button>
        </div>
        {area !== "reviewer" && (
          <div className="table-toolbar">
            <div className="tabs" role="group" aria-label="Filter articles">
              {[
                ["ALL", "All articles"],
                ["DRAFT", "Drafts"],
                ["IN_REVIEW", "In review"],
                ["REVIEWED", "Needs attention"],
                ["PUBLISH", "Published"],
              ].map(([value, label]) => (
                <button
                  className={filter === value ? "selected" : ""}
                  key={value}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="search-box">
              <Icon name="search" size={17} />
              <input
                aria-label="Search manuscripts on this page"
                placeholder="Search manuscripts…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
          </div>
        )}
        <ErrorNotice error={page.error} retry={page.reload} />
        {page.loading ? (
          <Loading />
        ) : (
          page.data &&
          (area === "reviewer" ? (
            <div className="assignment-list">
              {items.length ? (
                items.map((a) => (
                  <Link
                    key={a.id}
                    href={`/reviewer/assignments/${a.id}`}
                    className="assignment-row"
                  >
                    <span className="stat-icon">
                      <Icon name="article" />
                    </span>
                    <div>
                      <strong>
                        {a.title || a.article?.title || "Assigned manuscript"}
                      </strong>
                      <p>
                        {a.state} · Due {deadline(a.due_at)}
                      </p>
                      <small title={a.due_at}>UTC: {a.due_at}</small>
                    </div>
                    <span className="row-arrow">→</span>
                  </Link>
                ))
              ) : (
                <Empty title="Room for a new perspective">
                  Claim a manuscript from the review queue to get started.
                </Empty>
              )}
            </div>
          ) : (
            <ArticleTable
              area={area}
              articles={items.filter(
                (a) =>
                  (filter === "ALL" || a.status === filter) &&
                  a.title.toLowerCase().includes(search.toLowerCase()),
              )}
            />
          ))
        )}
        {page.data && (
          <div className="pagination">
            <span>{items.length} records on this page</span>
            <div className="actions">
              {cursor && (
                <button className="text-link" onClick={() => setCursor(null)}>
                  First page
                </button>
              )}
              {page.data.next_cursor && (
                <button
                  className="button secondary small"
                  onClick={() => setCursor(page.data!.next_cursor!)}
                >
                  Next page →
                </button>
              )}
            </div>
          </div>
        )}
      </section>
      <div className="bottom-grid">
        <section className="panel guide">
          <span className="eyebrow">THE PUBLISHING JOURNEY</span>
          <h2>Clarity at every step.</h2>
          <div className="journey">
            {[
              "Submit",
              "Expert review",
              "Refine & approve",
              "Payment & publish",
            ].map((step, i) => (
              <div key={step}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                <strong>{step}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="panel guide tip">
          <Icon name="leaf" />
          <h3>A little preparation goes a long way.</h3>
          <p>
            Check your outlet’s submission template, include your declarations,
            and keep a clean PDF or DOCX ready.
          </p>
          <Link href="/articles" className="text-link">
            Explore published work ↗
          </Link>
        </section>
      </div>
    </>
  );
}
