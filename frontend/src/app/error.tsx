"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main id="main-content" className="not-found">
      <h1>Let’s try that page again.</h1>
      <p className="subtle">Something interrupted your workspace.</p>
      <button className="button" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
