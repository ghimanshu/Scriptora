# Scriptora publishing backend

FastAPI backend for the workflow in [Application_Design.md](../Application_Design.md). This directory now contains executable source, nine Alembic migrations, PostgreSQL workers, private file adapters, and tests. The separate Next.js frontend/BFF is outside this backend implementation.

Implemented: verified author registration, Argon2id passwords, rotating refresh sessions with replay revocation, reviewer invitations/approval/subscriptions, taxonomy and immutable template/policy versions, draft/version submission, exclusive reviewer leases, revision reservations, feedback, invoices, payment reconciliation, publication, public catalog/downloads, notifications, audits, and idempotent business commands.

## Local setup (PowerShell)

Requires Python 3.12+ (tested with 3.13.14), Docker Desktop using Linux containers, and a running Docker engine. Resolved runtime and development dependencies are pinned in `requirements.lock`.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -r requirements.lock
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `JWT_SIGNING_KEY` in `.env` to the generated value. The placeholder is deliberately rejected. `.env`, private files, virtual environments, and test artifacts are ignored by Git. Never commit credentials. The default database password is for loopback development only; if changed, update `POSTGRES_PASSWORD`, `DATABASE_URL`, and `MIGRATION_DATABASE_URL` consistently. Percent-encode special characters in database URLs.

```powershell
docker compose up -d db mail scanner
alembic upgrade head
python -m app.cli seed-taxonomy
python -m app.cli create-admin --email admin@example.com
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Run the worker in a second activated terminal:

```powershell
python -m app.workers.main
```

The admin bootstrap securely prompts for a password and refuses an existing email or a second bootstrap while an active administrator exists. Seed data is idempotent and contains no default account/password. Configure real payment instructions through `POST /api/v1/admin/settings` before approving manuscripts; approval deliberately fails without a payment destination.

Documentation: http://127.0.0.1:8000/docs. Mail capture: http://127.0.0.1:8025. Health: `/api/v1/health/live` and `/api/v1/health/ready`. Readiness checks the database/schema; production additionally probes scanner and object storage. Monitor `worker_heartbeats` separately.

The browser calls the Next.js BFF on port 3000. FastAPI returns tokens only to the BFF, which must implement HttpOnly cookies, CSRF protection, and an explicit proxy allowlist. No cross-origin browser CORS policy is enabled here.

## API usage

The OpenAPI document at `/openapi.json` defines request payloads. `python -m scripts.export_openapi` writes `var/openapi.json` for frontend type generation.

Register with `POST /api/v1/auth/register`:

```json
{"email":"author@example.com","display_name":"Author","password":"a long unique passphrase"}
```

Follow the verification link captured in Mailpit; submit its token to `/auth/verify-email`. Login accepts email/password and returns `access_token`, `refresh_token`, and `expires_in`. Authenticated backend calls use `Authorization: Bearer <access_token>`.

Every authenticated JSON mutation requires `Idempotency-Key: <unique command identifier>`. Retrying an identical body/key returns the original response for 24 hours; changing its body returns 409. Registration/login/token operations and multipart uploads are exempt. Draft edits also require `If-Match: "<lock_version>"`; submit/claim/resubmit/reassign payloads use `expected_version`. A failed validation consumes no idempotency key.

An author creates a draft using subject, outlet, template IDs and metadata, uploads a manuscript with multipart `POST /files`, waits for `CLEAN`, attaches its ID, and submits. Metadata requires title, abstract where configured, keywords, author names/affiliations/emails, and true `originality`, `copyright`, and `conflict` declarations. PDF and DOCX word counts must meet the selected template. Files stay private and unavailable while scanning is pending or failed.

Approve an existing verified reviewer through `/admin/reviewers/{id}/approve`, or invite one through `/admin/reviewer-invitations`. Invitation acceptance sets the reviewer password and verified email; expertise subscriptions must match the article subject. Claim with `/articles/{id}/claim`, finalize feedback through `/assignments/{id}/review`. Approval requires a completed checklist and `required_changes_resolved=true`. There is no generic status-edit endpoint.

Deadlines use fresh PostgreSQL time after row locks. At `now >= due_at`, review writes fail and expire the lease even if the worker is stopped. Every assignment has a fixed 120-hour deadline with no extension. Resubmissions immediately assign the previous reviewer a fresh five-day review when they remain eligible, available, and within capacity. Otherwise the article returns to the queue and admins are notified. Disabling a reviewer/removing their role or subject revokes affected assignments. Availability controls new work while preserving access to existing assignments.

Approval snapshots one invoice for the accepted version. Proof upload never verifies payment. Administrators must separately confirm receipt/reference using `/admin/payment-attempts/{id}/verify`, then publish; `/admin/articles/{id}/verify-and-publish` performs both atomically. Authors cannot verify or publish their own articles, including multi-role users. Current publication supports the **same approved PDF** only. A DOCX acceptance requires a separately designed reviewer-confirmed PDF conversion workflow before publication; the API rejects arbitrary artifact substitution.

Public endpoints are `/public/articles`, `/public/articles/{slug}`, and `/public/articles/{slug}/download`. Private reviews, proofs, author email addresses, and unpublished manuscripts are excluded from public metadata.

## Containers and migrations

`compose.yaml` pins DB, mail, scanner, API and worker images. It uses loopback port bindings and persistent database/upload/signature volumes. ClamAV's first signature download can take several minutes. Start infrastructure and run migrations before starting API/worker containers. Containerized API and worker share the upload volume and use service DNS names; host commands use `.env` localhost URLs.

Build with `docker compose build api worker`, then `docker compose up -d api worker` after the migration job. API and worker use one backend image and separate commands. For production, inject secrets, use private PostgreSQL/network ingress, and run exactly one migration job per rollout. Never run ORM `create_all` during API startup.

Read [migrations/README.md](migrations/README.md). All revisions contain frozen schema operations independent of runtime model imports. `MIGRATION_DATABASE_URL` overrides `DATABASE_URL` for migration credentials. Use expand/backfill/contract for deployed breaking changes. Roll back only in disposable environments when safe; prefer reviewed roll-forward recovery for production.

## Checks

```powershell
pytest tests/unit tests/api
ruff check app tests migrations
ruff format --check app tests migrations
mypy app
python -m pip_audit -r requirements.lock
```

PostgreSQL integration tests require a **dedicated disposable database** named `publishing_test` or `scriptora_test`. Fixtures drop/recreate its public schema and truncate its tables; never point them at author/development/production data. Without `TEST_DATABASE_URL`, integration tests explicitly skip.

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://test_user:test_password@127.0.0.1:5432/publishing_test'
pytest tests/integration
```

The suite exercises fresh/prior migration upgrades, competing claims, deadline equality and late admission, revision reservations, payment/publication rollback, self-verification denial, idempotency, identity refresh replay, restart expiry, and deduplicated notification retries. Real PostgreSQL is required; SQLite cannot validate these locking guarantees. `scripts/check.ps1` and `scripts/ci.sh` run the checks. A hosted CI workflow template is in `ci/github-actions.yml`; install it under the repository-root `.github/workflows/` to activate it.

## Production and recovery assumptions

Set `APP_ENV=production`, a strong signing key, separate `OUTBOX_ENCRYPTION_KEY` (generate with `cryptography.fernet.Fernet.generate_key()`), `STORAGE_DRIVER=s3`, a private bucket, `SCANNER_DRIVER=clamav`, SMTP TLS/credentials, and an HTTPS public application URL. Production rejects local storage, scanner bypass, missing encryption key, and unsafe URL/mail settings. Provider credentials use the standard AWS SDK credential chain. Bucket access policies, encryption/key rotation, TLS ingress, limits/timeouts and backups are deployment responsibilities. Development derives outbox encryption from the signing key when no separate key is supplied. Keep encryption keys available until queued credentials have drained.

Outbox delivery uses leases, exponential retry and per-recipient deduplication. External email can duplicate after an ambiguous provider timeout; in-app notifications remain deduplicated. Failed jobs and scanner failures are visible to operators; monitor oldest pending event, `FAILED` rows, worker heartbeat, overdue leases, and payment backlog. Scanner and SMTP/object-storage adapters require provider smoke tests in the target deployment; the automated tests isolate external I/O.

Restore database and files to a consistent point, verify checksums and schema revision, start in restricted ingress, reconcile overdue leases/outbox delivery, then reopen traffic. Firm decisions still required: final taxonomy/template rules, bank details, invoice/tax wording, licensing, retention and conflict policy. Optional annotated-review uploads, DOI/ISSN issuance, post-publication corrections, advanced reporting and provider-specific operations require further integration; no launch certification or load/recovery guarantee is implied by the test suite.

Reviewer self-registration queues a REVIEWER_APPLICATION event for admins only. The outbox worker creates both in-app notifications and email deliveries. Admins review pending accounts at /admin/users and POST a reason to /admin/reviewers/{id}/approve or /reject. Email verification is not a prerequisite for an admin decision. Approval emails include an email-verification link for unverified accounts; reviewers must verify before signing in. Rejection emails include the decision reason, and rejected accounts cannot sign in as reviewers. Decisions are serialized and audited; completed applications leave the pending queue.

After updating to this version, run `alembic upgrade head` before restarting the API and `python -m app.workers.main`. Migration 0006_reviewer_decisions adds a rejection flag while preserving existing approvals. SMTP and the outbox worker must be running for emails and notifications to be delivered.


## Admin article deletion

Administrators can delete an article at any stage with `DELETE /api/v1/admin/articles/{article_id}` and JSON `{"reason":"Duplicate submission"}`. Send an `Idempotency-Key` and the usual authentication/CSRF headers. The admin article workspace includes a deletion form. Reasons are trimmed and must contain 3?2000 characters. The response is `{"deleted":true,"article_id":"..."}`. Retrying the same payload and key replays the response without duplicate email; a new deletion request for a deleted/missing article returns 404.

Deletion sets the article to `DELETED`, removes normal article/file and public publication access, revokes active/reserved reviews, and voids open invoices. Existing paid invoices, payments, publication records, and review/audit history remain stored. No automatic refund is issued. The administrator, prior status, and reason are recorded. An `ARTICLE_DELETED` outbox event queues an author notification and email containing the title, tracking number, and reason, including for inactive authors. Email delivery requires SMTP and the outbox worker.

Run `alembic upgrade head` for migration `0007_article_deletion`, then restart the API and worker. The frontend proxy permits the new admin DELETE endpoint.


Article workflow (migration 0008_article_workflow): DRAFT -> SUBMITTED -> ASSIGNED -> APPROVED -> PAID -> PAYMENT_APPROVED -> PUBLISH. Reviewer change requests set REJECTED; only the author can create a revised version and resubmit it. The previous reviewer is assigned a new five-day review by default; unavailable or ineligible previous reviewers trigger an admin notification and leave the article SUBMITTED. DRAFT records and their files, versions, and timeline are private to the author, including against administrator access. Admin lists exclude drafts. Approved subject-matched reviewers can inspect submitted articles before claiming. Admins choose an eligible reviewer with GET /admin/articles/{id}/reviewers and POST /admin/articles/{id}/assign; the legacy /reassign endpoint now has the same unassigned-only guard. Existing live assignments cannot be replaced. Both admin assignment and reviewer self-claim use article/reviewer locks and the unique live-assignment index.

Payment proof submission changes the article to PAID (awaiting verification). Admin receipt verification sets PAYMENT_APPROVED, and rejected proof returns it to APPROVED so corrected proof can be submitted. Publication remains a separate admin action and requires PAYMENT_APPROVED plus verified payment and the approved PDF. Approval emails include the snapshotted fee, instructions, and article link. The expiry worker returns overdue assignments to SUBMITTED.

Run alembic upgrade head before starting the updated API and worker. Migration 0008 maps existing IN_REVIEW/REVIEWED statuses, infers PAID/PAYMENT_APPROVED from payment records, converts old reserved assignments to active assignments, and fixes active review deadlines to five days from assignment. A previously extended active assignment can therefore become overdue; the expiry worker reconciles it. Stop older API/worker processes during deployment. Downgrading restores the old status vocabulary but does not restore previous deadline extensions or reservation states.


Draft classification (migration 0009_draft_subjects): the publication tab saves outlet_id and template_id immediately. publication_type_id is validated against the selected outlet and remains normalized in outlets.type_id rather than being duplicated on articles. primary_subject_id may be omitted or null for a DRAFT. The manuscript tab PATCHes the selected subject along with metadata; draft PATCH also accepts changes to publication_type_id, outlet_id, and template_id. Classification changes are validated together and update the draft version template. Only authors can change their own DRAFT classifications.

Selected primary subjects are stored in articles.primary_subject_id and synchronized to article_subjects. The migration backfills missing links for existing articles. Article details and author lists return the persisted subject/outlet labels and publication_type_id. Submission requires an active subject, and a database check prevents non-draft/non-deleted articles from having a null subject. Apply alembic upgrade head and restart the API/worker. Downgrade refuses while any article has no subject; choose subjects for those drafts first.


Revision resubmission preserves the original submitted version and structured responses. Authors can edit title/abstract and either retain the existing manuscript or upload a clean replacement. The reviewer who requested changes on the current submitted version is selected under a reviewer row lock, with the usual approval, subject, conflict, availability, and capacity checks. A new ACTIVE assignment starts immediately with a fresh 120-hour deadline; the article becomes ASSIGNED. This is not a reservation requiring the reviewer to start it. No schema migration is required for this resubmission policy change.
