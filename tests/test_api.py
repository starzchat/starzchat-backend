from datetime import timedelta

import pytest

from app import create_app
from app.cleanup import delete_expired_messages
from app.config import TestConfig
from app.extensions import db
from app.models import Message, SavedMessage, utcnow


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, username):
    res = client.post(
        "/api/auth/register",
        json={"student_id": username, "username": username, "password": "password123"},
    )
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.get_json()['token']}"}


def test_register_login_and_duplicates(client):
    register(client, "alice")
    same_id = client.post(
        "/api/auth/register",
        json={"student_id": "Alice", "username": "other", "password": "password123"},
    )
    assert same_id.status_code == 409  # that student ID already has an account
    same_name = client.post(
        "/api/auth/register",
        json={"student_id": "S4321", "username": "ALICE", "password": "password123"},
    )
    assert same_name.status_code == 409  # username already taken
    ok = client.post(
        "/api/auth/login", json={"username": "Alice", "password": "password123"}
    )
    assert ok.status_code == 200
    bad = client.post("/api/auth/login", json={"username": "alice", "password": "x"})
    assert bad.status_code == 401


def test_direct_message_flow(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat = client.post("/api/chats/direct", json={"student_id": "bob"}, headers=alice)
    chat_id = chat.get_json()["id"]

    again = client.post("/api/chats/direct", json={"student_id": "alice"}, headers=bob)
    assert again.get_json()["id"] == chat_id  # same 1:1 chat reused

    sent = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "hi bob"}, headers=alice
    )
    assert sent.status_code == 201
    msgs = client.get(f"/api/chats/{chat_id}/messages", headers=bob).get_json()
    assert [m["body"] for m in msgs] == ["hi bob"]


def test_outsider_cannot_read_or_send(client):
    alice = register(client, "alice")
    register(client, "bob")
    eve = register(client, "eve")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    assert client.get(f"/api/chats/{chat_id}/messages", headers=eve).status_code == 404
    assert (
        client.post(
            f"/api/chats/{chat_id}/messages", json={"body": "yo"}, headers=eve
        ).status_code
        == 404
    )


def test_group_admin_rules(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    register(client, "carol")
    group = client.post(
        "/api/chats/group",
        json={"name": "Study group", "members": ["bob"]},
        headers=alice,
    ).get_json()
    gid = group["id"]

    # Bob is not an admin, so he can't add people.
    denied = client.post(
        f"/api/chats/{gid}/members", json={"student_id": "carol"}, headers=bob
    )
    assert denied.status_code == 403
    added = client.post(
        f"/api/chats/{gid}/members", json={"student_id": "carol"}, headers=alice
    )
    assert added.status_code == 201
    # Members can leave on their own.
    assert client.delete(f"/api/chats/{gid}/members/bob", headers=bob).status_code == 200


def test_expiry_cleanup_and_save(app, client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    keep = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "keep me"}, headers=alice
    ).get_json()
    client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "forget me"}, headers=alice
    )

    # Bob saves one message, then time passes and everything expires.
    assert (
        client.post(f"/api/messages/{keep['id']}/save", headers=bob).status_code == 201
    )
    with app.app_context():
        for m in Message.query.all():
            m.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        assert delete_expired_messages() == 2
        assert Message.query.count() == 0
        assert SavedMessage.query.count() == 1

    saved = client.get("/api/saved", headers=bob).get_json()
    assert [s["body"] for s in saved] == ["keep me"]
    assert client.get("/api/saved", headers=alice).get_json() == []


def test_empty_message_rejected(client):
    alice = register(client, "alice")
    register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    res = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "   "}, headers=alice
    )
    assert res.status_code == 400


def test_socket_delivers_messages_to_members_only(app, client):
    from app.extensions import socketio

    alice_h, bob_h = register(client, "alice"), register(client, "bob")
    register(client, "eve")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice_h
    ).get_json()["id"]

    def token(headers):
        return headers["Authorization"].split()[1]

    alice = socketio.test_client(app, auth={"token": token(alice_h)})
    bob = socketio.test_client(app, auth={"token": token(bob_h)})
    eve_token = client.post(
        "/api/auth/login", json={"username": "eve", "password": "password123"}
    ).get_json()["token"]
    eve = socketio.test_client(app, auth={"token": eve_token})
    bad = socketio.test_client(app, auth={"token": "garbage"})

    from app.sockets import sid_to_user

    assert len(sid_to_user) == 3  # alice, bob, eve; the bad token was never registered
    del bad
    alice.emit("send_message", {"conversation_id": chat_id, "body": "hello"})
    assert [e["name"] for e in bob.get_received()] == ["new_message"]
    assert eve.get_received() == []

    eve.emit("send_message", {"conversation_id": chat_id, "body": "intrude"})
    assert eve.get_received()[0]["name"] == "error"


def test_removed_member_stops_receiving_socket_messages(app, client):
    """A member who is removed (or leaves) must stop getting live messages."""
    from app.extensions import socketio

    alice_h, bob_h = register(client, "alice"), register(client, "bob")
    gid = client.post(
        "/api/chats/group", json={"name": "Study group", "members": ["bob"]},
        headers=alice_h,
    ).get_json()["id"]

    def token(headers):
        return headers["Authorization"].split()[1]

    alice = socketio.test_client(app, auth={"token": token(alice_h)})
    bob = socketio.test_client(app, auth={"token": token(bob_h)})

    # Both are in the room now.
    alice.emit("send_message", {"conversation_id": gid, "body": "before"})
    assert [e["name"] for e in bob.get_received()] == ["new_message"]

    # The admin removes Bob.
    assert client.delete(f"/api/chats/{gid}/members/bob", headers=alice_h).status_code == 200

    alice.emit("send_message", {"conversation_id": gid, "body": "after"})
    assert bob.get_received() == [], "removed member must not receive new messages"


def test_leaving_group_stops_receiving_socket_messages(app, client):
    """The same must hold when a member leaves on their own."""
    from app.extensions import socketio

    alice_h, bob_h = register(client, "alice"), register(client, "bob")
    gid = client.post(
        "/api/chats/group", json={"name": "Study group", "members": ["bob"]},
        headers=alice_h,
    ).get_json()["id"]

    def token(headers):
        return headers["Authorization"].split()[1]

    alice = socketio.test_client(app, auth={"token": token(alice_h)})
    bob = socketio.test_client(app, auth={"token": token(bob_h)})

    assert client.delete(f"/api/chats/{gid}/members/bob", headers=bob_h).status_code == 200

    alice.emit("send_message", {"conversation_id": gid, "body": "after"})
    assert bob.get_received() == [], "member who left must not receive new messages"



def test_invalid_student_id_rejected(client):
    res = client.post(
        "/api/auth/register",
        json={"student_id": "no spaces!", "password": "password123"},
    )
    assert res.status_code == 400


def test_registration_is_open_to_anyone(client):
    """Anyone with a valid-looking student ID can register.

    There is no roster gate: the app is open, so any ID that matches the
    pattern is accepted.
    """
    res = client.post(
        "/api/auth/register",
        json={"student_id": "11387", "username": "ada", "password": "password123"},
    )
    assert res.status_code == 201
    headers = {"Authorization": f"Bearer {res.get_json()['token']}"}
    me = client.get("/api/me", headers=headers).get_json()
    assert me["student_id"] == "11387"
    assert me["username"] == "ada"

    # The display name is whatever the user typed, not an official one.
    named = client.post(
        "/api/auth/register",
        json={
            "student_id": "11388",
            "username": "bob",
            "password": "password123",
            "display_name": "Bob B",
        },
    )
    assert named.status_code == 201
    named_headers = {"Authorization": f"Bearer {named.get_json()['token']}"}
    assert (
        client.get("/api/me", headers=named_headers).get_json()["display_name"]
        == "Bob B"
    )


def test_add_chat_by_student_id_is_case_insensitive(client):
    alice = register(client, "S1001")
    register(client, "S1002")
    res = client.post("/api/chats/direct", json={"student_id": "s1002"}, headers=alice)
    assert res.status_code == 201
    assert res.get_json()["name"] == "S1002"
    unknown = client.post(
        "/api/chats/direct", json={"student_id": "S7777"}, headers=alice
    )
    assert unknown.status_code == 404


def test_username_is_required_and_validated(client):
    for payload in (
        {"student_id": "S1001", "password": "password123"},
        {"student_id": "S1001", "username": "a b", "password": "password123"},
        {"student_id": "S1001", "username": "ab", "password": "password123"},
    ):
        assert client.post("/api/auth/register", json=payload).status_code == 400


def test_user_search_finds_people_by_username_and_id(client):
    register(client, "alice")
    register(client, "bob")

    res = client.get("/api/users/search?q=bob", headers=register(client, "carol"))
    assert res.status_code == 200
    found = res.get_json()
    assert [u["username"] for u in found] == ["bob"]
    assert found[0]["student_id"] == "BOB"  # the ID a chat is started with

    # Case-insensitive, and matches a partial query.
    partial = client.get("/api/users/search?q=ALI", headers=register(client, "dave"))
    assert [u["username"] for u in partial.get_json()] == ["alice"]

    # An empty query returns nothing rather than the whole user list.
    empty = client.get("/api/users/search?q=", headers=register(client, "erin"))
    assert empty.get_json() == []


def test_user_search_requires_auth(client):
    assert client.get("/api/users/search?q=bob").status_code == 401


def test_user_search_rejects_bad_limit(client):
    headers = register(client, "alice")
    bad = client.get("/api/users/search?q=b&limit=abc", headers=headers)
    assert bad.status_code == 400



def test_messages_pagination(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    for i in range(10):
        client.post(f"/api/chats/{chat_id}/messages", json={"body": f"m{i}"}, headers=alice)

    # The newest page, limited to 3.
    page = client.get(f"/api/chats/{chat_id}/messages?limit=3", headers=bob).get_json()
    assert [m["body"] for m in page] == ["m7", "m8", "m9"]

    # Page backwards using the id of the oldest message in the page.
    before = page[0]["id"]
    older = client.get(
        f"/api/chats/{chat_id}/messages?limit=3&before={before}", headers=bob
    ).get_json()
    assert [m["body"] for m in older] == ["m4", "m5", "m6"]

    # Results are always oldest-first within a page.
    assert older[0]["id"] < older[-1]["id"]


def test_pagination_rejects_bad_parameters(client):
    alice = register(client, "alice")
    register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    assert (
        client.get(f"/api/chats/{chat_id}/messages?limit=abc", headers=alice).status_code
        == 400
    )
    assert (
        client.get(f"/api/chats/{chat_id}/messages?before=abc", headers=alice).status_code
        == 400
    )
    assert client.get(f"/api/chats/{chat_id}/messages?limit=0", headers=alice).status_code == 400


def test_unread_count_and_mark_as_read(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]

    client.post(f"/api/chats/{chat_id}/messages", json={"body": "hi"}, headers=alice)

    # Bob has not opened the chat, so he has an unread message.
    chats = client.get("/api/chats", headers=bob).get_json()
    assert chats[0]["unread_count"] == 1
    assert chats[0]["last_message_at"] is not None

    # Opening the chat marks it read.
    client.get(f"/api/chats/{chat_id}/messages", headers=bob)
    chats = client.get("/api/chats", headers=bob).get_json()
    assert chats[0]["unread_count"] == 0

    # A new message makes it unread again, and mark-as-read clears it.
    client.post(f"/api/chats/{chat_id}/messages", json={"body": "again"}, headers=alice)
    chats = client.get("/api/chats", headers=bob).get_json()
    assert chats[0]["unread_count"] == 1
    assert client.post(f"/api/chats/{chat_id}/read", headers=bob).status_code == 200
    chats = client.get("/api/chats", headers=bob).get_json()
    assert chats[0]["unread_count"] == 0


def test_chats_are_sorted_by_recency(client):
    alice = register(client, "alice")
    register(client, "bob")
    register(client, "carol")
    first = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    second = client.post(
        "/api/chats/direct", json={"student_id": "carol"}, headers=alice
    ).get_json()["id"]

    client.post(f"/api/chats/{first}/messages", json={"body": "old"}, headers=alice)
    client.post(f"/api/chats/{second}/messages", json={"body": "new"}, headers=alice)

    chats = client.get("/api/chats", headers=alice).get_json()
    assert [c["id"] for c in chats] == [second, first]


def test_group_ttl_can_be_validated_and_updated(client):
    alice, bob = register(client, "alice"), register(client, "bob")

    # A nonsense TTL is rejected at creation.
    bad = client.post(
        "/api/chats/group",
        json={"name": "g", "members": ["bob"], "ttl_seconds": -5},
        headers=alice,
    )
    assert bad.status_code == 400

    gid = client.post(
        "/api/chats/group",
        json={"name": "g", "members": ["bob"], "ttl_seconds": 3600},
        headers=alice,
    ).get_json()["id"]

    # Only admins can change it.
    denied = client.patch(f"/api/chats/{gid}/ttl", json={"ttl_seconds": 7200}, headers=bob)
    assert denied.status_code == 403

    ok = client.patch(f"/api/chats/{gid}/ttl", json={"ttl_seconds": 7200}, headers=alice)
    assert ok.status_code == 200
    assert ok.get_json()["ttl_seconds"] == 7200

    # A direct chat has no configurable expiry.
    direct = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    assert (
        client.patch(f"/api/chats/{direct}/ttl", json={"ttl_seconds": 7200}, headers=alice).status_code
        == 400
    )



def test_logout_revokes_the_token(client):
    headers = register(client, "alice")
    assert client.get("/api/me", headers=headers).status_code == 200

    assert client.post("/api/auth/logout", headers=headers).status_code == 200

    # The old token no longer works, so the user has to log in again.
    assert client.get("/api/me", headers=headers).status_code == 401


def test_logout_only_affects_that_user(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    client.post("/api/auth/logout", headers=alice)
    assert client.get("/api/me", headers=bob).status_code == 200


def test_change_password_revokes_old_tokens(client):
    headers = register(client, "alice")
    wrong = client.post(
        "/api/auth/password",
        json={"current_password": "nope", "new_password": "newpassword123"},
        headers=headers,
    )
    assert wrong.status_code == 403

    ok = client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "newpassword123"},
        headers=headers,
    )
    assert ok.status_code == 200

    # The old token is dead, but the returned one works.
    assert client.get("/api/me", headers=headers).status_code == 401
    new_headers = {"Authorization": f"Bearer {ok.get_json()['token']}"}
    assert client.get("/api/me", headers=new_headers).status_code == 200

    # The new password works for logging in.
    login = client.post(
        "/api/auth/login", json={"username": "alice", "password": "newpassword123"}
    )
    assert login.status_code == 200


def test_change_password_rejects_short_password(client):
    headers = register(client, "alice")
    res = client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "short"},
        headers=headers,
    )
    assert res.status_code == 400


def test_update_display_name(client):
    headers = register(client, "alice")
    res = client.patch("/api/me", json={"display_name": "Alice A"}, headers=headers)
    assert res.status_code == 200
    assert res.get_json()["display_name"] == "Alice A"
    assert client.get("/api/me", headers=headers).get_json()["display_name"] == "Alice A"


def test_revoked_token_cannot_connect_a_socket(app, client):
    from app.extensions import socketio

    headers = register(client, "alice")
    token = headers["Authorization"].split()[1]
    client.post("/api/auth/logout", headers=headers)

    # The socket refuses a connection with a revoked token.
    revoked = socketio.test_client(app, auth={"token": token})
    assert not revoked.is_connected()




def test_rate_limit_blocks_flooding(app, client):
    """Too many login attempts in a row are rejected with 429."""
    app.config["RATE_LIMIT_LOGIN"] = "3/minute"
    for _ in range(3):
        client.post(
            "/api/auth/login", json={"username": "alice", "password": "wrong"}
        )
    blocked = client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert blocked.status_code == 429


def test_sender_can_edit_their_message(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    message = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "typo"}, headers=alice
    ).get_json()

    edited = client.patch(
        f"/api/messages/{message['id']}", json={"body": "fixed"}, headers=alice
    )
    assert edited.status_code == 200
    assert edited.get_json()["body"] == "fixed"
    assert edited.get_json()["edited_at"] is not None

    # The list shows the new body too.
    msgs = client.get(f"/api/chats/{chat_id}/messages", headers=bob).get_json()
    assert [m["body"] for m in msgs] == ["fixed"]


def test_only_the_sender_can_edit_a_message(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    message = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "mine"}, headers=alice
    ).get_json()

    denied = client.patch(
        f"/api/messages/{message['id']}", json={"body": "hijacked"}, headers=bob
    )
    assert denied.status_code == 403


def test_sender_can_delete_their_message(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    message = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "oops"}, headers=alice
    ).get_json()

    denied = client.delete(f"/api/messages/{message['id']}", headers=bob)
    assert denied.status_code == 403

    assert client.delete(f"/api/messages/{message['id']}", headers=alice).status_code == 200
    msgs = client.get(f"/api/chats/{chat_id}/messages", headers=bob).get_json()
    assert msgs == []


def test_outsider_cannot_edit_a_message(client):
    alice = register(client, "alice")
    register(client, "bob")
    eve = register(client, "eve")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    message = client.post(
        f"/api/chats/{chat_id}/messages", json={"body": "private"}, headers=alice
    ).get_json()

    # An outsider gets 404, not 403, so the chat is not revealed.
    assert (
        client.patch(
            f"/api/messages/{message['id']}", json={"body": "x"}, headers=eve
        ).status_code
        == 404
    )


def test_typing_indicator_is_relayed_to_the_room(app, client):
    from app.extensions import socketio

    alice_h, bob_h = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice_h
    ).get_json()["id"]

    def token(headers):
        return headers["Authorization"].split()[1]

    alice = socketio.test_client(app, auth={"token": token(alice_h)})
    bob = socketio.test_client(app, auth={"token": token(bob_h)})

    alice.emit("typing", {"conversation_id": chat_id, "is_typing": True})
    received = bob.get_received()
    assert [e["name"] for e in received] == ["typing"]
    assert received[0]["args"][0]["username"] == "alice"

    # The sender does not receive their own indicator.
    assert alice.get_received() == []


def test_read_receipt_updates_the_unread_count(app, client):
    from app.extensions import socketio

    alice_h, bob_h = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice_h
    ).get_json()["id"]

    def token(headers):
        return headers["Authorization"].split()[1]

    alice = socketio.test_client(app, auth={"token": token(alice_h)})
    bob = socketio.test_client(app, auth={"token": token(bob_h)})

    alice.emit("send_message", {"conversation_id": chat_id, "body": "hi"})
    sent = client.get(f"/api/chats/{chat_id}/messages", headers=alice_h).get_json()
    message_id = sent[-1]["id"]

    bob.emit("read_receipt", {"conversation_id": chat_id, "message_id": message_id})
    chats = client.get("/api/chats", headers=bob_h).get_json()
    assert chats[0]["unread_count"] == 0



def test_delete_account_removes_the_user_and_their_messages(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"student_id": "bob"}, headers=alice
    ).get_json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"body": "bye"}, headers=alice)

    assert client.delete("/api/me", headers=alice).status_code == 200

    # The account is gone, so the token no longer works.
    assert client.get("/api/me", headers=alice).status_code == 401

    # Bob's chat stays, but Alice's message went with her.
    msgs = client.get(f"/api/chats/{chat_id}/messages", headers=bob).get_json()
    assert msgs == []


def test_delete_account_leaves_the_group_with_an_admin(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    gid = client.post(
        "/api/chats/group", json={"name": "Study group", "members": ["bob"]},
        headers=alice,
    ).get_json()["id"]

    assert client.delete("/api/me", headers=alice).status_code == 200

    # Bob is still in the group and is now its admin.
    chats = client.get("/api/chats", headers=bob).get_json()
    assert [c["id"] for c in chats] == [gid]

