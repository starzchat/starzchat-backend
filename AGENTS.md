# AGENTS.md

## If you are an AI agent working on the frontend

**Read [`FRONTEND_HANDOFF.md`](FRONTEND_HANDOFF.md) in full before writing any code.**
It contains the complete API contract (REST + Socket.IO), response shapes, validation
rules, error semantics, the suggested feature order, and a list of backend gaps you
must flag rather than work around.

Key points up front:

- This repo is **backend only** (Python/Flask). Do not modify it to make the frontend
  easier — use the API as documented, and ask for backend changes.
- The live contract is also available at `GET /api/docs` on a running server.
- `app/static/` is a throwaway demo client, not the production frontend.
- The API is stable. If you need a new field or endpoint, request it rather than
  working around its absence — see the "Backend gaps" section of the handoff.

## If you are an AI agent working on the backend

- Stack: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Flask-SocketIO,
  APScheduler, pytest, ruff.
- Run tests: `pytest -q`. Lint: `ruff check .`.
- Schema is managed by **Alembic** (`migrations/` is committed). If you change a model in
  `app/models.py`, you must generate and commit a migration with it:
  ```bash
  flask --app run db migrate -m "short description"
  flask --app run db upgrade          # applies it to your local database
  ```
  Never rely on `db.create_all()` to pick up a model change — it only creates *missing
  tables*, it never adds a column to an existing one, so the change would work on a
  fresh database and silently break on Supabase. Do not edit a migration that has
  already been applied; add a new one instead.
- `AUTO_CREATE_SCHEMA` (default `true`) controls whether the app creates missing tables
  on startup. It is a development convenience only. Set it to `false` in production and
  run `flask --app run db upgrade` as a deploy step instead. The app skips schema
  creation automatically for `flask db ...` CLI calls, so autogenerate works correctly.
- `flask --app run db stamp head` marks a database as being at the current migration
  **without running any SQL**. Use it for an existing database whose schema was created
  by `create_all()` — it does not touch data.
- `flask --app run db downgrade` rolls back one migration. Use it if a migration was
  applied by mistake; it is the only safe way to undo a schema change on a database
  that holds real data (`reset-db` drops everything).
- Timestamps are stored **naive UTC** on purpose (see `app/models.py:utcnow`) so SQLite
  and Postgres behave identically. Keep that convention.
- Authorisation is centralised in `app/services.py:require_member`, which raises `404`
  (not `403`) for non-members so chat existence is not leaked. New routes that touch
  conversation data should go through it.
- Message expiry is enforced in two places on purpose: a read-time filter in
  `app/chats.py` and the APScheduler job in `app/cleanup.py`. Keep both.
