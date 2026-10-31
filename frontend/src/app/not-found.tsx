import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main-content" className="not-found">
      <div className="eyebrow">404 · A PAGE STILL UNWRITTEN</div>
      <h1>This chapter couldn’t be found.</h1>
      <p className="subtle">The page may have moved or may be unavailable.</p>
      <Link className="button" href="/">
        Back to Scriptora →
      </Link>
    </main>
  );
}
