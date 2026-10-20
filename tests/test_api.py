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
        "/api/auth/register", json={"username": username, "password": "password123"}
    )
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.get_json()['token']}"}


def test_register_login_and_duplicates(client):
    register(client, "alice")
    dup = client.post(
        "/api/auth/register", json={"username": "Alice", "password": "password123"}
    )
    assert dup.status_code == 409
    ok = client.post(
        "/api/auth/login", json={"username": "alice", "password": "password123"}
    )
    assert ok.status_code == 200
    bad = client.post("/api/auth/login", json={"username": "alice", "password": "x"})
    assert bad.status_code == 401


def test_direct_message_flow(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat = client.post("/api/chats/direct", json={"username": "bob"}, headers=alice)
    chat_id = chat.get_json()["id"]

    again = client.post("/api/chats/direct", json={"username": "alice"}, headers=bob)
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
        "/api/chats/direct", json={"username": "bob"}, headers=alice
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
        f"/api/chats/{gid}/members", json={"username": "carol"}, headers=bob
    )
    assert denied.status_code == 403
    added = client.post(
        f"/api/chats/{gid}/members", json={"username": "carol"}, headers=alice
    )
    assert added.status_code == 201
    # Members can leave on their own.
    assert client.delete(f"/api/chats/{gid}/members/bob", headers=bob).status_code == 200


def test_expiry_cleanup_and_save(app, client):
    alice, bob = register(client, "alice"), register(client, "bob")
    chat_id = client.post(
        "/api/chats/direct", json={"username": "bob"}, headers=alice
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
        "/api/chats/direct", json={"username": "bob"}, headers=alice
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
        "/api/chats/direct", json={"username": "bob"}, headers=alice_h
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
