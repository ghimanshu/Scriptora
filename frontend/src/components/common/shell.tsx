"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "./icon";
import { useResource, ErrorNotice } from "./data";
import { api } from "@/lib/api-client";
import type { Role, User } from "@/types/api";
const nav = {
  author: [
    ["", "Overview", "grid"],
    ["/articles", "My articles", "article"],
    ["/articles/new", "New submission", "plus"],
  ],
  reviewer: [
    ["", "Overview", "grid"],
    ["/queue", "Review queue", "book"],
    ["/assignments", "My assignments", "article"],
    ["/profile", "Expertise & availability", "people"],
  ],
  admin: [
    ["", "Overview", "grid"],
    ["/articles", "All articles", "article"],
    ["/payments", "Payment verification", "check"],
    ["/users", "People & reviewers", "people"],
    ["/settings", "Settings & templates", "settings"],
    ["/audit", "Audit trail", "clock"],
  ],
};
export type Area = keyof typeof nav;
export function Brand() {
  return (
    <Link href="/" className="brand">
      <span className="brand-symbol">
        <Icon name="book" size={23} />
      </span>
      <span>
        scriptora<span className="brand-dot">.</span>
      </span>
    </Link>
  );
}
export function Shell({
  area,
  children,
}: {
  area: Area;
  children: React.ReactNode;
}) {
  const path = usePathname();
  const router = useRouter();
  const { data: user } = useResource<User>("/me");
  const [error, setError] = useState<Error>();
  const role = area.toUpperCase() as Role;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-scroll">
        <Brand />
        <div className="workspace-label">PUBLISHING WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {nav[area].map(([href, label, icon]) => (
            <Link
              key={href}
              href={`/${area}${href}`}
              className={
                (href === "" ? path === `/${area}` : path === `/${area}${href}`)
                  ? "nav-item active"
                  : "nav-item"
              }
            >
              <Icon name={icon} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <Icon name="leaf" />
            <strong>Ideas deserve an audience.</strong>
            <p>Thoughtful publishing, from first draft to final page.</p>
            <Link href="/articles">
              Explore publications <span>↗</span>
            </Link>
          </div>
          <Link className="nav-item" href={`/${area}/notifications`}>
            <Icon name="bell" />
            Notifications
          </Link>
        </div>
        </div>
        <div className="sidebar-footer">
          <div className="user-card">
            <span className="avatar">
              {user?.name?.slice(0, 2).toUpperCase() || "SC"}
            </span>
            <div>
              <strong>{user?.name || "Your workspace"}</strong>
              <small>{area.charAt(0).toUpperCase() + area.slice(1)}</small>
            </div>
          </div>
            <button
              type="button"
              className="sidebar-logout"
              onClick={async () => {
                try {
                  await api("/auth/logout", { method: "POST" });
                  router.push("/login");
                } catch (e) {
                  setError(e as Error);
                }
              }}
            >
              <Icon name="exit" size={17} />
              Log out
            </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            <strong>{area.charAt(0).toUpperCase() + area.slice(1)}</strong>
          </div>
          <div className="topbar-actions">
            <Link href="/articles" className="text-link">
              Public library <span>↗</span>
            </Link>
            {user && user.roles.length > 1 && (
              <select
                aria-label="Switch workspace"
                value={role}
                onChange={(e) =>
                  router.push(`/${e.target.value.toLowerCase()}`)
                }
              >
                {user.roles.map((r) => (
                  <option key={r} value={r}>
                    {r.toLowerCase()}
                  </option>
                ))}
              </select>
            )}
            <Link
              href={`/${area}/notifications`}
              className="icon-button"
              aria-label="Notifications"
            >
              <Icon name="bell" />
            </Link>
            <span className="avatar small">
              {user?.name?.slice(0, 1) || "S"}
            </span>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <ErrorNotice error={error} />
          {user && !user.roles.includes(role) ? (
            <div className="notice error" role="alert">
              This workspace requires the {area} role.{" "}
              <Link href={`/${user.roles[0]?.toLowerCase() || "login"}`}>
                Open your workspace
              </Link>
            </div>
          ) : (
            children
          )}
        </main>
        <footer className="workspace-footer">
          <span>© {new Date().getFullYear()} Scriptora Publishing</span>
          <span>Carefully reviewed. Confidently published.</span>
        </footer>
      </div>
    </div>
  );
}
