from flask import request
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_socketio import disconnect, emit, join_room
from jwt.exceptions import PyJWTError

from .extensions import db, socketio
from .models import Member, User
from .services import ChatError, create_message, require_member

# user_id -> set of socket ids, so REST actions can add live users to new rooms.
connected_users = {}
sid_to_user = {}


def token_is_current(user_id, token_version):
    """True when a token was issued after the last logout / password change.

    The token carries the version that was current when it was issued, and the
    user row carries the current one. A mismatch means the token has been
    revoked, so it must not be accepted any more.
    """
    if token_version is None:
        # A token issued before this feature existed: accept it.
        return True
    user = db.session.get(User, user_id)
    if user is None:
        return False
    return user.token_version == token_version


@socketio.on("connect")
def on_connect(auth):
    token = (auth or {}).get("token")
    try:
        claims = decode_token(token)
        user_id = int(claims["sub"])
    except (JWTExtendedException, PyJWTError, KeyError, TypeError, ValueError):
        return False  # reject the connection

    # A token that was revoked by a logout or password change is refused too.
    if not token_is_current(user_id, claims.get("ver")):
        return False

    sid_to_user[request.sid] = user_id
    connected_users.setdefault(user_id, set()).add(request.sid)
    for (conversation_id,) in db.session.query(Member.conversation_id).filter_by(
        user_id=user_id
    ):
        join_room(f"chat:{conversation_id}")


@socketio.on("disconnect")
def on_disconnect(*_):
    user_id = sid_to_user.pop(request.sid, None)
    if user_id is not None:
        connected_users.get(user_id, set()).discard(request.sid)


@socketio.on("send_message")
def on_send_message(data):
    user_id = sid_to_user.get(request.sid)
    if user_id is None:
        disconnect()
        return
    try:
        message = create_message(
            (data or {}).get("conversation_id"), user_id, (data or {}).get("body")
        )
    except ChatError as err:
        emit("error", {"error": err.message})
        return
    emit("new_message", message.to_dict(), to=f"chat:{message.conversation_id}")


@socketio.on("typing")
def on_typing(data):
    """Tell the other people in the chat that this user is typing.

    The indicator is not stored anywhere; it is relayed to the room as it is.
    """
    user_id = sid_to_user.get(request.sid)
    if user_id is None:
        disconnect()
        return
    conversation_id = (data or {}).get("conversation_id")
    try:
        require_member(conversation_id, user_id)
    except ChatError:
        return  # not a member: do not leak anything about the chat

    user = db.session.get(User, user_id)
    emit(
        "typing",
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "username": user.username if user else None,
            "is_typing": bool((data or {}).get("is_typing", True)),
        },
        to=f"chat:{conversation_id}",
        include_self=False,
    )


@socketio.on("read_receipt")
def on_read_receipt(data):
    """Record that this user has read the chat up to a given message id."""
    user_id = sid_to_user.get(request.sid)
    if user_id is None:
        disconnect()
        return
    conversation_id = (data or {}).get("conversation_id")
    try:
        membership = require_member(conversation_id, user_id)
    except ChatError:
        return

    try:
        message_id = int((data or {}).get("message_id", 0))
    except (TypeError, ValueError):
        message_id = 0

    if message_id > membership.last_read_message_id:
        membership.last_read_message_id = message_id
        db.session.commit()
        emit(
            "read_receipt",
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "message_id": membership.last_read_message_id,
            },
            to=f"chat:{conversation_id}",
            include_self=False,
        )


@socketio.on("presence")
def on_presence(data):
    """Tell the room who is online right now."""
    user_id = sid_to_user.get(request.sid)
    if user_id is None:
        disconnect()
        return
    conversation_id = (data or {}).get("conversation_id")
    try:
        require_member(conversation_id, user_id)
    except ChatError:
        return

    user = db.session.get(User, user_id)
    emit(
        "presence",
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "username": user.username if user else None,
            "online": True,
        },
        to=f"chat:{conversation_id}",
        include_self=False,
    )
