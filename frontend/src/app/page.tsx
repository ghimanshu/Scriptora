import Link from "next/link";
import { PublicFrame } from "@/components/common/public";
import { Icon } from "@/components/common/icon";
export default function Home() {
  return (
    <PublicFrame>
      <section className="hero">
        <div>
          <div className="eyebrow">A HOME FOR IDEAS THAT MATTER</div>
          <h1>
            From a first draft
            <br />
            to a <em>lasting impact.</em>
          </h1>
          <p>
            Bring your research to a thoughtful community of authors, expert
            reviewers, and readers. We’ll help your next chapter find its
            audience.
          </p>
          <div className="actions">
            <Link href="/register" className="button">
              Start your publishing journey <Icon name="arrow" size={17} />
            </Link>
            <Link href="/articles" className="text-link">
              Explore publications ↗
            </Link>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="book-illustration">
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
            <div className="orbit" />
            <div className="orbit orbit-two" />
            <span className="spark">✳</span>
          </div>
        </div>
      </section>
      <div className="public-grid">
        {[
          [
            "article",
            "A considered submission",
            "A clear, guided process for your manuscript, supporting files, and declarations.",
          ],
          [
            "people",
            "An expert perspective",
            "Subject-qualified reviewers provide structured feedback to help your ideas become stronger.",
          ],
          [
            "book",
            "A wider conversation",
            "Approved work joins a public library of carefully reviewed publications.",
          ],
        ].map(([icon, title, text]) => (
          <section className="article-card" key={title}>
            <span className="stat-icon">
              <Icon name={icon} />
            </span>
            <h2>{title}</h2>
            <p>{text}</p>
          </section>
        ))}
      </div>
    </PublicFrame>
  );
}
