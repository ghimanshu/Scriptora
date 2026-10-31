# Database migrations

Executable Alembic revisions implement the backend schema in order:

1. `0001_identity_taxonomy`: identity, sessions/tokens, taxonomy/issues, templates and settings.
2. `0002_articles_files`: private file metadata, articles, immutable versions and authors.
3. `0003_reviews_workflow`: rounds, exclusive assignments, feedback/responses/history and deferred circular references.
4. `0004_payments_publications`: invoices, attempts, publication and partial payment uniqueness indexes.
5. `0005_outbox_audit`: durable events, deliveries, notifications, audit/idempotency and worker heartbeat.

Run `alembic upgrade head` with a validated signing key and `MIGRATION_DATABASE_URL` (fallback `DATABASE_URL`). URLs use `postgresql+psycopg`. Credentials are never stored in `alembic.ini`. The API checks the head revision in readiness; migrations run as one deployment job rather than per replica.

Revisions contain explicit frozen operations. New schema changes require a new reviewed revision; never regenerate already deployed history. Review constraints, indexes and backfills. Run `pytest tests/integration` with an explicit allowlisted disposable `TEST_DATABASE_URL` to test a fresh schema and upgrade from the previous revision. Fixtures are destructive only on that dedicated test database.

Downgrades remove data and are suitable only for disposable environments or an explicitly reviewed recovery plan. Never downgrade a production deployment automatically. Use separate least-privilege runtime credentials, database/file backups, expand/backfill/contract migrations and verified roll-forward recovery.
