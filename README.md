# Article Publishing Platform — development design package

Start with Application_Design.md for requirements, policy defaults, architecture, state machine, schema, API contract, security, operational design and acceptance criteria.

- frontend/README.md and frontend/.env.example specify the separate Next.js frontend/BFF setup.
- backend/README.md and backend/.env.example specify FastAPI/PostgreSQL setup.
- backend/migrations/README.md specifies the Alembic migration sequence.

This package is a development specification and configuration template set. It does not contain runnable applications or claim passing application tests. Build the two target codebases using the design, then replace setup commands with verified project instructions.

Important defaults: five elapsed days per assignment; revision reservation starts at resubmission; expiry returns to the subject reviewer pool; article state remains APPROVED through payment verification; admin publication requires verified payment and the approved immutable version.
