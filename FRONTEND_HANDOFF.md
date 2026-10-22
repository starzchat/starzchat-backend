# StarzChat — Frontend Handoff

**Read this first if you are an AI agent picking up the frontend work.**

This repository is the **backend only**. It is finished and working. Your job is to
build the **web client** that talks to it. Do not modify the backend to make the
frontend easier — instead, use the API as documented below.

- **Backend:** Python 3 / Flask (SQLAlchemy, JWT, Socket.IO, APScheduler)
- **Frontend:** not started
- **Status:** backend MVP complete, 11/11 tests passing, `ruff` clean

> **Note on `app/static/`:** the demo client (vanilla JS) is committed to git as a
> **reference implementation** — it is the fastest way to see every endpoint and event
> working. It is *not* the production frontend and it is not a template to copy
> (it uses `innerHTML` + a manual `escapeHtml` helper). Build the real client from
> this document; feel free to delete `app/static/` if it gets in the way.

---

## 1. What the app is

StarzChat is a **text-only chat web app for university students**.

The defining product rule: **messages self-delete after a TTL** (default 24 hours) to
keep backend storage costs low — *unless* a user explicitly saves a private copy.
Saving makes a **per-user copy**; the original still expires for everyone else.

Feature checklist:

- Register with **student ID** + a **username you choose** + password; log in with username + password
- **Registration is open** to anyone with a valid-looking student ID (no roster)
- Start a **1:1 chat** by entering someone's student ID; create **group chats** by listing student IDs
- Groups have **admin** and **member** roles
- **Real-time** delivery over Socket.IO
- **Per-group expiry**: a group can override the default 24h TTL
- **Save a message** to keep a private copy that outlives the original

---

## 2. Repository layout

```
app/
  __init__.py    app factory, blueprints, CLI commands
  config.py      settings (env driven)
  models.py      User, Conversation, Member, Message, SavedMessage
  auth.py        register / login / me
  chats.py       chats, groups, members, messages, saved messages
  sockets.py     real-time events
  services.py    shared message logic + permission checks
  cleanup.py     expired-message deletion
  api_docs.py    GET /api/docs -> machine-readable route contract
  static/        demo client (vanilla JS, reference implementation). Replace freely.
migrations/      Alembic migrations (database schema history)
tests/           pytest suite (backend)
run.py           dev server entrypoint
```

---

## 3. Running the backend

```bash
cd starzchat-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit the secrets
python run.py               # http://127.0.0.1:5000
```

Useful endpoints on a running server:

| URL | What |
| --- | --- |
| `http://127.0.0.1:5000/api/docs` | **Live JSON route contract** — read this to confirm paths |
| `http://127.0.0.1:5000/health` | Health check |

Backend tests: `pytest -q`  ·  Lint: `ruff check .`

### CORS is already handled for you

The backend enables CORS on `/api/*` and on the Socket.IO transport.

| Env var | Default | Purpose |
| --- | --- | --- |
| `CORS_ORIGINS` | `*` | Browser origins allowed to call the API |
| `SOCKETIO_CORS_ORIGINS` | `*` | Socket.IO client origins |
| `API_BASE_URL` | `http://127.0.0.1:5000` | Public base URL, reported by `/api/docs` |
| `SERVE_FRONTEND` | `true` | Serve the bundled demo UI. Set `false` once your client is a separate app |

**Before deploying**, set `CORS_ORIGINS` / `SOCKETIO_CORS_ORIGINS` to your real
frontend origin instead of `*`, and replace the placeholder secrets in `.env`.

---

## 4. API contract

Base URL: `http://127.0.0.1:5000` (set `VITE_API_URL` / `NEXT_PUBLIC_API_URL` etc. to match).

### Auth model

All routes except register/login require a JWT bearer token.

```
Authorization: Bearer <token>
```

`POST /api/auth/register` returns `201` with a token **already included** — no
separate login call is needed after registering.

### Endpoints

| Method | Route | Auth | Body / Notes |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | no | `{student_id, username, password, display_name?}` → `201 {token, username}` |
| `POST` | `/api/auth/login` | no | `{username, password}` → `{token, username}` |
| `GET` | `/api/me` | yes | → `{id, username, student_id, display_name}` |
| `GET` | `/api/chats` | yes | → array of conversations |
| `POST` | `/api/chats/direct` | yes | `{student_id}` → conversation (**reuses an existing 1:1 chat**, so it may not be `201`) |
| `POST` | `/api/chats/group` | yes | `{name, members: [student_id], ttl_seconds?}` → `201` conversation |
| `POST` | `/api/chats/<id>/members` | yes | admin only → `{student_id}` → `201` conversation |
| `DELETE` | `/api/chats/<id>/members/<username>` | yes | admin removes member, or anyone removes themselves → `{ok: true}` |
| `GET` | `/api/chats/<id>/messages` | yes | → array of live messages |
| `POST` | `/api/chats/<id>/messages` | yes | `{body}` → `201` message |
| `POST` | `/api/messages/<id>/save` | yes | → `201` saved copy |
| `GET` | `/api/saved` | yes | → array of saved copies (newest first) |
| `DELETE` | `/api/saved/<id>` | yes | → `{ok: true}` |

### Response shapes

```jsonc
// Conversation
{
  "id": 12,
  "kind": "direct",          // "direct" | "group"
  "name": "bob",             // for direct chats this is the OTHER person's username
                              // for groups it's the group name
  "members": ["alice", "bob"] // usernames
}

// Message
{
  "id": 88,
  "conversation_id": 12,
  "sender": "alice",         // username
  "body": "hello",
  "created_at": "2026-10-21T22:30:00Z",
  "expires_at": "2026-10-22T22:30:00Z"
}

// SavedMessage
{
  "id": 5,
  "conversation_id": 12,
  "sender": "alice",
  "body": "hello",
  "original_created_at": "2026-10-21T22:30:00Z",
  "saved_at": "2026-10-21T22:35:00Z"
}
```

### Errors

Always the same shape — read `error`:

```json
{ "error": "Only admins can add members" }
```

Common statuses: `400` validation, `401` bad credentials, `403` not admin,
`404` not found **or not a member**, `409` duplicate (student ID or username taken).

> **Important:** the backend returns **`404`, not `403`, when you are not a member of a
> conversation** — it deliberately does not reveal that the chat exists. Don't render
> "you don't have access"; just show an empty/not-found state.

### Validation rules (enforced server-side)

- `username`: `^[A-Za-z0-9_]{3,32}$`, unique, **case-insensitive**
- `password`: minimum 8 characters
- `student_id`: matched against `STUDENT_ID_PATTERN` (default `^[A-Z0-9-]{3,20}$`),
  **stored upper-case** — always send it upper-case and compare upper-case
- message body: non-empty after trimming, max 2000 chars
- group name: required, max 80 chars

The backend **returns the token on register**, so the client should store it and skip
the login screen.

---

## 5. Real-time (Socket.IO)

The backend speaks **Socket.IO v4** (protocol compatible with `socket.io-client` v4).

```js
import { io } from 'socket.io-client';

const socket = io(BASE_URL, { auth: { token } });
```

- The server validates the JWT in `auth.token` at connect time and **rejects the
  connection** if it is missing or invalid. Listen for `connect_error` and send the
  user back to the login screen.
- On connect the server **auto-joins you to every chat room you belong to** — you do
  not need to join rooms yourself.
- Room names are `chat:<conversation_id>`.

| Direction | Event | Payload |
| --- | --- | --- |
| client → server | `send_message` | `{conversation_id, body}` |
| server → client | `new_message` | a Message object (same shape as the REST response) |
| server → client | `error` | `{error: "..."}` |

**Sending: pick one path and stick to it.**

- `POST /api/chats/<id>/messages` → returns the created message (201) **and** emits
  `new_message` to the room. This is the path the demo client uses and it is the most
  convenient, because the sender gets the canonical server object back.
- Socket `send_message` → the server emits `new_message` to the room, including to
  you. But the sender receives **no direct return value** from the emit, so you must
  wait for the `new_message` round-trip. There is no acknowledgement callback.

If you use the socket path, expect your own message to arrive via the `new_message`
listener — do **not** also optimistically append it locally, or you will duplicate it.
The demo client guards against this with an `if (document.getElementById('msg-'+m.id)) return;` check.

Other server-side room behaviour to be aware of: when a chat is created or a member is
added over REST, the server pushes already-connected members into the new room, so
they receive messages immediately without reconnecting.

---

## 6. Suggested client architecture

The frontend stack is **your choice** — React/Vue/Svelte/SvelteKit/Next, plain TS, etc.
Nothing in the backend constrains it.

Minimum viable feature set, in suggested order:

1. **Auth screen** — login + register tabs; store the token (e.g. `localStorage`); on
   boot, call `GET /api/me` to validate a stored token and, on `401`, log out
2. **Chat list** — `GET /api/chats`, with a "start 1:1 by student ID" input
3. **Message view** — `GET /api/chats/<id>/messages`, render sender + timestamp
4. **Composer** — `POST /api/chats/<id>/messages`, optimistic UI optional
5. **Real-time** — connect the socket, append `new_message` as it arrives
6. **Save message** — a per-message "Save copy" button → `POST /api/messages/<id>/save`
7. **Saved messages panel** — `GET /api/saved`, `DELETE /api/saved/<id>`
8. **Groups** — create group, add member, leave group, admin-only controls

### Things the UI must get right

- **Expiry is visible in the data.** Each message carries `expires_at`. Show a
  countdown or "expires in 24h" affordance so the self-deleting behaviour is not
  surprising — it is the product's core idea.
- **Messages disappear.** When a message's `expires_at` passes, remove it from the
  view (a local timer is enough). The backend also stops returning it.
- **Escape all user-supplied text.** Usernames, display names, group names and message
  bodies are arbitrary strings. Never inject them as HTML.
- **Student IDs are upper-case.** Normalise before sending and when comparing.
- **The demo client is a reference, not a template.** `app/static/app.js` (if present)
  uses `innerHTML` with an `escapeHtml` helper — replicate the escaping, or better, use
  a framework's templating and drop the helper entirely.

---

## 7. Backend facts you should not have to rediscover

- **Outsiders get `404`, not `403`** — membership is checked before existence is
  revealed, on every read and write.
- **1:1 chats are deduplicated.** `POST /api/chats/direct` returns the existing chat
  if one already exists between those two users.
- **You cannot start a chat with yourself.**
- **Group creator is the admin.** Only admins can add members or remove others.
- **Anyone can remove themselves** from a group (leave).
- **If the last admin leaves, the backend promotes another member automatically** —
  groups never become admin-less.
- **Direct chats have no member management.** Only groups support add/remove.
- **Registration is open.** Any student ID matching the server's pattern can sign
  up; there is no roster. The `display_name` is whatever the user typed, so the
  client should display it when present and fall back to `username`.
- **Saved messages are private.** `GET /api/saved` returns only the caller's own copies.
- **Saved copies outlive the original** but can be deleted by their owner.
- **The API shape is stable.** Existing fields will not be renamed or removed
  without a version bump; new optional fields may be added, so **ignore unknown
  fields** in responses rather than validating strictly against a fixed schema.
- **The database schema is version-controlled** with Alembic (`migrations/`), and the
  live Supabase database is stamped at the current revision. If the backend adds a
  field, it arrives with a migration — you do not need to do anything on the
  frontend side, and you should not expect the frontend to trigger schema changes.

---

## 8. Known backend gaps — flag them, don't work around them silently

If you hit one of these, report it to the backend owner rather than patching the
backend yourself:

| Gap | Impact on the frontend |
| --- | --- |
| **No push notifications / email** | Out of scope. |
| **SQLite by default** | Fine locally. `psycopg` is already installed — production uses Postgres via `DATABASE_URL`. |
| **Migrations are manual** | Schema changes are applied by the backend owner with `flask db upgrade`. You never need to run migrations. |
| **Rate-limit counters are in-process** | The limits themselves are enforced per IP, but with several workers each has its own counter. Redis (`RATELIMIT_STORAGE_URI`) shares them. |

### Gaps that have since been closed

These were listed as gaps before and are now implemented:

| Was | Now |
| --- | --- |
| No pagination on `GET /api/chats/<id>/messages` | `?limit=` and `?before=<message id>`; results are oldest-first within a page. `GET /api/chats` takes `?limit=&offset=`. |
| No rate limiting on login or send | `429` after the limit in `.env` (`RATE_LIMIT_LOGIN`, `RATE_LIMIT_REGISTER`, `RATE_LIMIT_SEND`). |
| No message edit/delete by sender | `PATCH` / `DELETE /api/messages/<id>`; only the sender may do this. |
| No read receipts / typing indicators | Socket.IO `typing` and `read_receipt` events, plus `POST /api/chats/<id>/read` and an `unread_count` on each chat. |
| `ttl_seconds` is set only at group creation | `PATCH /api/chats/<id>/ttl` (admin only). |
| No presence/online list | Socket.IO `presence` event. |
| No way to find a student ID | `GET /api/users/search?q=` returns usernames *and* student IDs. |
| No logout / token revocation | `POST /api/auth/logout` and `POST /api/auth/password` invalidate every token for that user. |

---

## 9. Definition of done for the frontend

- Register, log in, log out, and token persistence across reloads
- List chats; start a 1:1 chat by student ID; create a group
- Send and receive messages in real time between two browser tabs
- Read-only access to a conversation you are not a member of is impossible from the UI's perspective (server enforces it; the UI should handle `404` gracefully)
- Save a message and view/delete saved copies
- Group admin controls (add member, remove member, leave)
- A visible expiry affordance on messages
- No XSS via usernames, group names or message bodies

---

## 10. Ground rules

1. **Do not edit the backend.** If the API is missing something you need, write it down
   and ask — a coordinated backend change is cheap, a divergent fork is not.
2. **Treat `GET /api/docs` as the source of truth** for paths and methods.
3. **Don't trust the client.** All validation, authorisation and expiry is server-side;
   your UI is a view over that, never the enforcer.
4. **Never log or commit tokens**, and don't store them anywhere less safe than
   `localStorage`/`sessionStorage` without understanding the XSS tradeoff.
5. **Keep the demo UI in `app/static/` working or delete it** — but don't mix new
   frontend code into the Python package.

