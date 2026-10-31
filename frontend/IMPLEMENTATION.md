# Frontend implementation

This checkout now contains the Next.js application specified by README.md and ../Application_Design.md. The separate backend still contains specifications only. Data operations require that backend; no successful business workflows or demo records are simulated.

## Run

Use Node 24.22.2 LTS (`.node-version`, Dockerfile). Install with `npm ci`, copy `.env.example` to `.env.local`, then `npm run dev`. Open http://localhost:3000. Workspaces: `/author`, `/reviewer`, `/admin`; accounts: `/register`, `/verify-email`, `/login`, `/forgot-password`, `/reset-password`.

Implemented screens cover public home/catalog/article/download; author dashboard/list/submission wizard/version and review history/revision responses/payment proof/timeline; reviewer queue/conflicts/claim/reserved-start/feedback drafts/checklists/decisions/release/expertise/availability; admin articles/reassignment/extensions/reviewer invitation and approval/account activation/payments/publication/taxonomy/templates/issues/settings/audit; and notifications for all roles. Counts explicitly describe the current page, not global totals.

## Security and deployment

The BFF uses explicit method/path allowlisting, a fixed private upstream, selected forwarded headers, no redirects, bounded streaming, timeouts, no-store and sanitized errors with request IDs. Tokens stay in HttpOnly SameSite=Lax cookies. Authenticated mutations require exact Origin and session-bound signed CSRF cookie/header. Public account mutations also require Origin. Browser code only calls relative `/api/v1/*`.

Production startup requires explicit origins, secure cookies and three distinct `__Host-` cookie names. Set COOKIE*SECURE=true; use trusted HTTPS ingress and private backend networking. Inject secrets/configuration at runtime. No backend configuration uses NEXT_PUBLIC*. Align ingress/backend/BFF upload limits and shared rate limits. Backend authorization and MIME/signature/scanning/clean-file checks remain authoritative.

Refresh is explicit and workflow commands are never automatically replayed. Web Locks coordinate browser refreshes; BFF refresh deduplication is process-local. Configure sticky sessions or a shared coordinator before deploying multiple replicas. Docker runs standalone Next.js as non-root; Docker and pinned Node 24 validation must be completed in the deployment environment. Checks here use host Node 26.4.0.

## Contract boundary and remaining work

The backend OpenAPI schema is unavailable. `src/types/api.generated.ts` is an empty placeholder, deliberately not fabricated generated output. `src/types/api.ts` records provisional UI contract assumptions: `{items,next_cursor}` lists, taxonomy template_id, backend allowed_actions, invoice instructions, and reviews nested in versions. Reconcile these with canonical backend responses before claiming end-to-end support.

Set OPENAPI_SCHEMA_URL to the real backend schema and run `npm run api:generate`; commit generated output and adapt UI models. To check drift in repository CI, regenerate and run `git diff --exit-code -- frontend/src/types/api.generated.ts` from the repository root. No repository-level CI was installed outside this writable frontend directory.

Alternatively, `npm run api:check` generates into a temporary directory and exits nonzero on contract drift. Both commands fail explicitly when the schema URL is unavailable.

Template/issue/settings administration currently uses backend-schema JSON editors pending schemas. Full saved-draft metadata editing, server feedback-draft restoration, admin role editing, operational aggregate metrics and template-specific form rendering remain follow-ups. The submission wizard collects complete baseline metadata; saved-draft editing covers title/abstract/manuscript.

## Verification

Commands: `npm run lint`, `npm run typecheck`, `npm test`, `npx playwright install chromium`, `npm run test:e2e`, `npm run build`, `npm audit --omit=dev`.

Unit tests exercise BFF allowlisting, origin/session CSRF binding, secure configuration, authentication gating, sanitized error propagation, redirect rejection and streamed forwarding. Playwright checks public registration navigation, author empty/filter/error states, mobile overflow and BFF rejection paths. UI data responses are intercepted in browser tests, not real backend integration.

Set TEST_BACKEND_URL to a disposable real backend to opt into readiness/OpenAPI/authentication integration tests; they skip when absent. Full submit/review/revise/approve/proof/verify/publish acceptance, concurrency, scanning, email, permission, migration and recovery tests require the backend and remain unverified. Production dependencies and development tooling are audited separately.

For 502 errors, check backend connectivity; for 401 explicitly renew/sign in; for CSRF failures verify exact APP_ORIGIN and cookie/HTTPS settings; for 409/412 preserve input and reconcile refreshed state before retrying. Do not blindly retry commands with new idempotency keys.

## Verified results

Lint, TypeScript, production build, nine unit/security tests and eight desktop/mobile Playwright tests passed on this host. One actual-backend integration test was skipped because TEST_BACKEND_URL was absent. Desktop/mobile dashboard screenshots were inspected. The deployed dependency audit reports zero vulnerabilities; the full audit reports 18 moderate development-tooling advisories, primarily transitive minimatch dependencies. No Docker execution or complete backend workflow was verified.
