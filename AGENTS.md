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

## If you are an AI agent working on the backend

- Stack: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Flask-SocketIO,
  APScheduler, pytest, ruff.
- Run tests: `pytest -q`. Lint: `ruff check .`.
- Schema changes currently use `db.create_all()` at startup; there is no
  `migrations/` directory yet. Migrations are on the roadmap — if you change a model,
  say so rather than silently relying on `create_all()`.
- Timestamps are stored **naive UTC** on purpose (see `app/models.py:utcnow`) so SQLite
  and Postgres behave identically. Keep that convention.
- Authorisation is centralised in `app/services.py:require_member`, which raises `404`
  (not `403`) for non-members so chat existence is not leaked. New routes that touch
  conversation data should go through it.
- Message expiry is enforced in two places on purpose: a read-time filter in
  `app/chats.py` and the APScheduler job in `app/cleanup.py`. Keep both.
