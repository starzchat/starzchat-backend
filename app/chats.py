from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from .extensions import db, socketio
from .models import Conversation, Member, Message, SavedMessage, User, utcnow
from .services import (
    ChatError,
    create_message,
    get_membership,
    normalize_id,
    require_member,
)

bp = Blueprint("chats", __name__, url_prefix="/api")


@bp.errorhandler(ChatError)
def handle_chat_error(err):
    return jsonify(error=err.message), err.status


def current_user_id():
    return int(get_jwt_identity())


def find_user(student_id):
    user = User.query.filter_by(student_id=normalize_id(student_id)).first()
    if user is None:
        raise ChatError(f"No student found with ID '{student_id}'", 404)
    return user


def find_user_by_username(username):
    user = User.query.filter(
        db.func.lower(User.username) == (username or "").strip().lower()
    ).first()
    if user is None:
        raise ChatError(f"No student found with username '{username}'", 404)
    return user


def conversation_dict(conv, user_id):
    members = [m.user.username for m in conv.members]
    name = conv.name
    if conv.kind == "direct":
        others = [m.user.username for m in conv.members if m.user_id != user_id]
        name = others[0] if others else "(you)"
    return {"id": conv.id, "kind": conv.kind, "name": name, "members": members}


def join_user_to_room(user_id, conversation_id):
    """Best effort: nothing to do unless the user is connected over a socket."""
    from .sockets import connected_users

    for sid in list(connected_users.get(user_id, set())):
        try:
            socketio.server.enter_room(sid, f"chat:{conversation_id}", namespace="/")
        except (KeyError, ValueError):
            # That socket already disconnected; drop it and carry on.
            connected_users[user_id].discard(sid)


@bp.get("/chats")
@jwt_required()
def list_chats():
    uid = current_user_id()
    convs = (
        Conversation.query.join(Member)
        .filter(Member.user_id == uid)
        .order_by(Conversation.id)
        .all()
    )
    return jsonify([conversation_dict(c, uid) for c in convs])


@bp.post("/chats/direct")
@jwt_required()
def start_direct():
    uid = current_user_id()
    other = find_user((request.get_json(silent=True) or {}).get("student_id"))
    if other.id == uid:
        raise ChatError("You can't start a chat with yourself")

    # Reuse the existing 1:1 chat if there is one.
    mine = db.session.query(Member.conversation_id).filter_by(user_id=uid)
    existing = (
        Conversation.query.join(Member)
        .filter(
            Conversation.kind == "direct",
            Member.user_id == other.id,
            Conversation.id.in_(mine),
        )
        .first()
    )
    if existing:
        return jsonify(conversation_dict(existing, uid))

    conv = Conversation(kind="direct", created_by=uid)
    conv.members = [Member(user_id=uid), Member(user_id=other.id)]
    db.session.add(conv)
    db.session.commit()
    for member_id in (uid, other.id):
        join_user_to_room(member_id, conv.id)
    return jsonify(conversation_dict(conv, uid)), 201


@bp.post("/chats/group")
@jwt_required()
def create_group():
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 80:
        raise ChatError("Group name is required (max 80 characters)")

    member_ids = {uid}
    for student_id in data.get("members") or []:
        member_ids.add(find_user(student_id).id)

    conv = Conversation(
        kind="group", name=name, created_by=uid, ttl_seconds=data.get("ttl_seconds")
    )
    conv.members = [
        Member(user_id=mid, role="admin" if mid == uid else "member")
        for mid in member_ids
    ]
    db.session.add(conv)
    db.session.commit()
    for member_id in member_ids:
        join_user_to_room(member_id, conv.id)
    return jsonify(conversation_dict(conv, uid)), 201


@bp.post("/chats/<int:chat_id>/members")
@jwt_required()
def add_member(chat_id):
    uid = current_user_id()
    me = require_member(chat_id, uid)
    conv = db.session.get(Conversation, chat_id)
    if conv.kind != "group":
        raise ChatError("Only group chats can have members added")
    if me.role != "admin":
        raise ChatError("Only admins can add members", 403)

    user = find_user((request.get_json(silent=True) or {}).get("student_id"))
    if get_membership(chat_id, user.id):
        raise ChatError("Already a member", 409)
    db.session.add(Member(conversation_id=chat_id, user_id=user.id))
    db.session.commit()
    join_user_to_room(user.id, chat_id)
    return jsonify(conversation_dict(conv, uid)), 201


@bp.delete("/chats/<int:chat_id>/members/<username>")
@jwt_required()
def remove_member(chat_id, username):
    uid = current_user_id()
    me = require_member(chat_id, uid)
    conv = db.session.get(Conversation, chat_id)
    if conv.kind != "group":
        raise ChatError("Only group chats support removing members")

    target = find_user_by_username(username)
    if target.id != uid and me.role != "admin":
        raise ChatError("Only admins can remove other members", 403)
    membership = get_membership(chat_id, target.id)
    if membership is None:
        raise ChatError("Not a member", 404)

    db.session.delete(membership)
    db.session.commit()

    # If the last admin leaves, promote someone so the group isn't orphaned.
    remaining = Member.query.filter_by(conversation_id=chat_id).all()
    if remaining and not any(m.role == "admin" for m in remaining):
        remaining[0].role = "admin"
        db.session.commit()
    return jsonify(ok=True)


@bp.get("/chats/<int:chat_id>/messages")
@jwt_required()
def list_messages(chat_id):
    require_member(chat_id, current_user_id())
    messages = (
        Message.query.filter(
            Message.conversation_id == chat_id, Message.expires_at > utcnow()
        )
        .order_by(Message.id)
        .all()
    )
    return jsonify([m.to_dict() for m in messages])


@bp.post("/chats/<int:chat_id>/messages")
@jwt_required()
def post_message(chat_id):
    message = create_message(
        chat_id, current_user_id(), (request.get_json(silent=True) or {}).get("body")
    )
    payload = message.to_dict()
    socketio.emit("new_message", payload, to=f"chat:{chat_id}")
    return jsonify(payload), 201


@bp.post("/messages/<int:message_id>/save")
@jwt_required()
def save_message(message_id):
    uid = current_user_id()
    message = db.session.get(Message, message_id)
    if message is None or message.expires_at <= utcnow():
        raise ChatError("Message not found", 404)
    require_member(message.conversation_id, uid)

    # Saving makes a private copy, so the original can still expire for everyone.
    saved = SavedMessage(
        user_id=uid,
        conversation_id=message.conversation_id,
        sender_username=message.sender.username,
        body=message.body,
        original_created_at=message.created_at,
    )
    db.session.add(saved)
    db.session.commit()
    return jsonify(saved.to_dict()), 201


@bp.get("/saved")
@jwt_required()
def list_saved():
    rows = (
        SavedMessage.query.filter_by(user_id=current_user_id())
        .order_by(SavedMessage.saved_at.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows])


@bp.delete("/saved/<int:saved_id>")
@jwt_required()
def delete_saved(saved_id):
    row = SavedMessage.query.filter_by(
        id=saved_id, user_id=current_user_id()
    ).first()
    if row is None:
        raise ChatError("Saved message not found", 404)
    db.session.delete(row)
    db.session.commit()
    return jsonify(ok=True)
