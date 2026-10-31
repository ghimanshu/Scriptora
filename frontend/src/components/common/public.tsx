import Link from "next/link";
import { Brand } from "./shell";
export function PublicFrame({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="public-header">
        <Brand />
        <nav aria-label="Main navigation">
          <Link href="/articles">Publications</Link>
          <Link href="/login">Sign in</Link>
          <Link href="/register" className="button">
            Become an author ↗
          </Link>
        </nav>
      </header>
      <main id="main-content" className="public-main">
        {children}
      </main>
      <footer className="public-footer">
        <span>© {new Date().getFullYear()} Scriptora Publishing</span>
        <span>Thoughtful publishing. Lasting impact.</span>
      </footer>
    </>
  );
}
