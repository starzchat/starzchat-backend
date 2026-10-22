# StarzChat Backend

> **Building the web client?** Read **[FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md)** first —
> it has the full API contract, Socket.IO events, and the list of things this backend
> does *not* do. This repo is backend-only; the frontend lives in its own app.

A text-only chat app built with Python and Flask. Users can send direct messages and create group chats. Messages delete themselves after a set time to keep backend costs low, unless a user saves them.

## Features

- Students sign up with their **student ID**, a **username** they choose and their own password; they log in with username + password (JWT)
- Optional roster check, so only IDs on the university's list can register
- Add another student by their ID to start chatting; create groups by listing student IDs
- One-to-one chats and group chats (admin and member roles)
- Real-time delivery with Flask-SocketIO, including typing indicators and read receipts
- Self-deleting messages (default 24 hours, configurable per group)
- Save a message to keep your own private copy after the original expires
- Edit or delete your own messages
- Unread badges, chat recency sorting and paginated history
- Logout and password change revoke every token already issued
- Rate limiting on login, registration and sending

## How message expiry works

- Every message gets an `expires_at` timestamp when it is created (indexed for fast cleanup).
- A background job (APScheduler) runs every `CLEANUP_INTERVAL` seconds and deletes rows where `expires_at <= now`.
- Saving a message copies it into `saved_messages` for that user only. The original still expires for everyone, and the saved copy stays until the user deletes it.
- You can also run the cleanup by hand: `flask --app run cleanup`.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then edit the secrets
python run.py            # http://127.0.0.1:5000
```

Run the tests and linter:

```bash
pytest -q
ruff check .
```

## API overview

All routes except register/login need the header `Authorization: Bearer <token>`.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register` | Create account `{student_id, username, password, display_name?}` |
| POST | `/api/auth/login` | Log in `{username, password}`, returns a token |
| POST | `/api/auth/logout` | Revoke every token issued for this user |
| POST | `/api/auth/password` | Change password `{current_password, new_password}`, returns a fresh token |
| GET | `/api/me` | Current user |
| PATCH | `/api/me` | Update `{display_name}` |
| DELETE | `/api/me` | Delete the account, its messages and its chats |
| GET | `/api/users/search` | Find people `?q=&limit=` (username, name or student ID) |
| GET | `/api/chats` | List my chats `?limit=&offset=` (newest activity first) |
| POST | `/api/chats/direct` | Start or reuse a 1:1 chat `{student_id}` |
| POST | `/api/chats/group` | Create group `{name, members: [student IDs], ttl_seconds?}` |
| POST | `/api/chats/<id>/members` | Add member (admin only) `{student_id}` |
| DELETE | `/api/chats/<id>/members/<username>` | Remove member (admin) or leave (self) |
| PATCH | `/api/chats/<id>/ttl` | Change a group's expiry (admin only) `{ttl_seconds}` |
| POST | `/api/chats/<id>/read` | Mark the chat as read, clearing the unread badge |
| GET | `/api/chats/<id>/messages` | List live messages `?limit=&before=<message id>` |
| POST | `/api/chats/<id>/messages` | Send a message `{body}` |
| PATCH | `/api/messages/<id>` | Edit your own message `{body}` |
| DELETE | `/api/messages/<id>` | Delete your own message |
| POST | `/api/messages/<id>/save` | Save a private copy |
| GET | `/api/saved` | List my saved messages |
| DELETE | `/api/saved/<id>` | Delete a saved message |
| GET | `/api/roster` | List the allowed student IDs (roster mode) |
| POST | `/api/roster` | Add a student ID to the roster |
| DELETE | `/api/roster/<student_id>` | Remove a student ID from the roster |

### Rate limits

Requests are limited per client IP and answered with `429` when the limit is
hit. The defaults are in `.env` (`RATE_LIMIT_LOGIN`, `RATE_LIMIT_REGISTER`,
`RATE_LIMIT_SEND`, `RATE_LIMIT_DEFAULT`).

### Student IDs and the roster

- Chats and messages show usernames only; a student ID is only used to add someone.
- IDs are stored upper-case and matched case-insensitively. The allowed format is set by `STUDENT_ID_PATTERN` in `.env`.
- To stop people registering with someone else's ID, load the university's list and turn the check on:

```bash
# students.csv has the columns: student_id,full_name
flask --app run import-roster students.csv
# then set REQUIRE_ROSTER=true in .env
```

- With the roster on, the official name from the list is used as the display name.
- Development only: `flask --app run reset-db` drops and recreates all tables.

### Real-time (Socket.IO)

Connect with `auth: {token: "<jwt>"}`. You are joined to all your chat rooms automatically.

- Emit `send_message` with `{conversation_id, body}`
- Emit `typing` with `{conversation_id, is_typing}`
- Emit `read_receipt` with `{conversation_id, message_id}`
- Emit `presence` with `{conversation_id}`
- Listen for `new_message`, `message_updated`, `message_deleted` (payload is the
  message), `typing`, `read_receipt`, `presence` and `error`

A token that was revoked by a logout or password change is refused at connect
time, and the socket is dropped from the rooms when a member is removed.

## Database migrations

The schema is managed by **Alembic** (`migrations/` is committed to git). Supabase is
already stamped at the current revision, so nothing needs to be applied there yet.

```bash
flask --app run db migrate -m "add user nickname"   # generate a migration
flask --app run db upgrade                           # apply it
flask --app run db downgrade                         # roll back one migration
flask --app run db current                           # show the applied revision
```

If you change `app/models.py`, generate a migration with it and commit both. The app
creates missing tables on startup for convenience (`AUTO_CREATE_SCHEMA=true`), but that
never adds a column to an existing table — only Alembic does that.

## Project layout

```
app/
  __init__.py    app factory, blueprints, CLI command
  config.py      settings (env driven)
  models.py      User, AllowedStudent, Conversation, Member, Message, SavedMessage
  auth.py        register / login
  chats.py       chats, groups, messages, saved messages
  sockets.py     real-time events
  services.py    shared message logic and permission checks
  cleanup.py     expired-message deletion
  api_docs.py    GET /api/docs route contract
  static/        demo client (vanilla JS, reference implementation)
migrations/      Alembic migrations (schema history)
tests/           pytest suite
```

## Roadmap

- Redis-backed Socket.IO message queue for multi-worker deployment
- A web client

## License

MIT
