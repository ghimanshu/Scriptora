"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { DeleteArticle } from "./delete-article";
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
  onDeleted,
}: {
  articles: Article[];
  area?: "author" | "admin";
  onDeleted?: () => void;
}) {
  const router = useRouter();
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
            <th>ACTIONS</th>
          </tr>
        </thead>
        <tbody>
          {articles.map((article) => (
            <tr key={article.id}>
              <td>
                <Link className="article-title" href={`/${area}/articles/${article.id}`}>
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
                <div className="actions">
                  {area === "admin" && <button type="button" className="button secondary small"
                    onClick={() => router.push(`/${area}/articles/${article.id}`)}>
                    View
                  </button>}
                  {area === "author" && article.status === "DRAFT" && (
                    <DeleteArticle articleId={article.id} title={article.title || "Untitled manuscript"} onDeleted={onDeleted} />
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
