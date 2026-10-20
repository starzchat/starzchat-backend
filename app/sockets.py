from flask import request
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_socketio import disconnect, emit, join_room
from jwt.exceptions import PyJWTError

from .extensions import db, socketio
from .models import Member
from .services import ChatError, create_message

# user_id -> set of socket ids, so REST actions can add live users to new rooms.
connected_users = {}
sid_to_user = {}


@socketio.on("connect")
def on_connect(auth):
    token = (auth or {}).get("token")
    try:
        user_id = int(decode_token(token)["sub"])
    except (JWTExtendedException, PyJWTError, KeyError, TypeError, ValueError):
        return False  # reject the connection

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
