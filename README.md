# StarzChat Backend

A text-only chat app built with Python and Flask. Users can send direct messages and create group chats. Messages delete themselves after a set time to keep backend costs low, unless a user saves them.

## Features

- Username + password sign-up and login (JWT)
- One-to-one chats and group chats (admin and member roles)
- Real-time delivery with Flask-SocketIO
- Self-deleting messages (default 24 hours, configurable per group)
- Save a message to keep your own private copy after the original expires

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
| POST | `/api/auth/register` | Create account `{username, password}` |
| POST | `/api/auth/login` | Log in, returns a token |
| GET | `/api/me` | Current user |
| GET | `/api/chats` | List my chats |
| POST | `/api/chats/direct` | Start or reuse a 1:1 chat `{username}` |
| POST | `/api/chats/group` | Create group `{name, members: [...], ttl_seconds?}` |
| POST | `/api/chats/<id>/members` | Add member (admin only) `{username}` |
| DELETE | `/api/chats/<id>/members/<username>` | Remove member (admin) or leave (self) |
| GET | `/api/chats/<id>/messages` | List live messages |
| POST | `/api/chats/<id>/messages` | Send a message `{body}` |
| POST | `/api/messages/<id>/save` | Save a private copy |
| GET | `/api/saved` | List my saved messages |
| DELETE | `/api/saved/<id>` | Delete a saved message |

### Real-time (Socket.IO)

Connect with `auth: {token: "<jwt>"}`. You are joined to all your chat rooms automatically.

- Emit `send_message` with `{conversation_id, body}`
- Listen for `new_message` (payload is the message) and `error`

## Project layout

```
app/
  __init__.py    app factory, scheduler, CLI command
  config.py      settings (env driven)
  models.py      User, Conversation, Member, Message, SavedMessage
  auth.py        register / login
  chats.py       chats, groups, messages, saved messages
  sockets.py     real-time events
  services.py    shared message logic and permission checks
  cleanup.py     expired-message deletion
tests/           pytest suite
```

## Roadmap

- Alembic migrations (`flask db init`) instead of `create_all`
- Rate limiting on login and sending
- PostgreSQL + Redis (Socket.IO message queue) for deployment
- A web client

## License

MIT
