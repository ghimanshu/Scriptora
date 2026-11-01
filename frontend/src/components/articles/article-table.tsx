import Link from "next/link";
import type { Article } from "@/types/api";
import { date, statusLabels } from "@/lib/formatting";
import { Empty } from "@/components/common/data";
export function Status({ status }: { status: Article["status"] }) {
  return (
    <span className={`badge status-${status}`}>
      <span />
      {statusLabels[status]}
    </span>
  );
}
export function ArticleTable({
  articles,
  area = "author",
}: {
  articles: Article[];
  area?: "author" | "admin";
}) {
  if (!articles.length)
    return (
      <Empty title="Your next chapter starts here">
        {area === "author" ? (
          <>
            Create a draft to begin your publication journey.{" "}
            <Link href="/author/articles/new">Start a submission →</Link>
          </>
        ) : (
          "Articles will appear here as authors submit their work."
        )}
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>ARTICLE</th>
            <th>STATUS</th>
            <th>SUBMITTED</th>
            <th>VERSION</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {articles.map((article) => (
            <tr key={article.id}>
              <td>
                <Link
                  href={`/${area}/articles/${article.id}`}
                  className="article-title"
                >
                  {article.title || "Untitled manuscript"}
                </Link>
                <small>
                  {article.subject || "Subject pending"}
                  {article.outlet ? ` · ${article.outlet}` : ""}
                </small>
              </td>
              <td>
                <Status status={article.status} />
              </td>
              <td>{date(article.created_at)}</td>
              <td>
                <span className="version">
                  v{article.current_version_number || 1}
                </span>
              </td>
              <td>
                <Link
                  className="row-arrow"
                  href={`/${area}/articles/${article.id}`}
                  aria-label={`Open ${article.title}`}
                >
                  {area === "author" && article.status === "DRAFT"
                    ? "Edit draft"
                    : area === "author" && article.status === "REJECTED"
                      ? "Revise article"
                      : "↗"}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
