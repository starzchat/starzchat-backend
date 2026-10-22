"""Authentication: registration, login, logout and account settings.

Tokens are JWTs that stay valid for a week, so they need a way to be
revoked. Every token carries the user's `token_version` at the time it was
issued; bumping that column invalidates every token issued before it. That
is how logging out or changing a password takes effect immediately.
"""

import re

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
)

from .extensions import db, limiter
from .models import Conversation, Member, Message, SavedMessage, User
from .services import ChatError, normalize_id

bp = Blueprint("auth", __name__, url_prefix="/api")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def find_by_username(username):
    return User.query.filter(
        db.func.lower(User.username) == (username or "").strip().lower()
    ).first()


def issue_token(user):
    """Create a token that is bound to the user's current token_version."""
    return create_access_token(
        identity=str(user.id), additional_claims={"ver": user.token_version}
    )


@bp.post("/auth/register")
@limiter.limit(lambda: current_app.config["RATE_LIMIT_REGISTER"])
def register():
    data = request.get_json(silent=True) or {}
    student_id = normalize_id(data.get("student_id"))
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()[:80]

    if not re.match(current_app.config["STUDENT_ID_PATTERN"], student_id):
        return jsonify(error="Enter a valid student ID"), 400
    if not USERNAME_RE.match(username):
        return jsonify(error="Username must be 3-32 letters, numbers or _"), 400
    if len(password) < 8:
        return jsonify(error="Password must be at least 8 characters"), 400
    if User.query.filter_by(student_id=student_id).first():
        return jsonify(error="An account with this student ID already exists"), 409
    if find_by_username(username):
        return jsonify(error="Username already taken"), 409

    user = User(
        student_id=student_id, username=username, display_name=display_name or None
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    token = issue_token(user)
    return jsonify(token=token, username=user.username), 201


@bp.post("/auth/login")
@limiter.limit(lambda: current_app.config["RATE_LIMIT_LOGIN"])
def login():
    data = request.get_json(silent=True) or {}
    user = find_by_username(data.get("username"))
    if user is None or not user.check_password(data.get("password") or ""):
        # Same message for both cases, so usernames can't be probed through login.
        return jsonify(error="Invalid username or password"), 401
    token = issue_token(user)
    return jsonify(token=token, username=user.username)


@bp.post("/auth/logout")
@jwt_required()
def logout():
    """Invalidate every token already issued for this user.

    The tokens themselves stay cryptographically valid until they expire, but
    they stop being accepted because the stored version no longer matches.
    """
    user = db.session.get(User, int(get_jwt_identity()))
    user.token_version += 1
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/auth/password")
@jwt_required()
def change_password():
    """Change the password. All existing tokens are revoked."""
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""

    if not user.check_password(current):
        raise ChatError("Current password is incorrect", 403)
    if len(new) < 8:
        raise ChatError("New password must be at least 8 characters")
    if new == current:
        raise ChatError("New password must be different from the current one")

    user.set_password(new)
    # Changing the password signs out every other device.
    user.token_version += 1
    db.session.commit()
    # A fresh token, so the device that made the change stays logged in.
    return jsonify(ok=True, token=issue_token(user))


@bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    return jsonify(
        id=user.id,
        username=user.username,
        student_id=user.student_id,
        display_name=user.display_name,
    )


@bp.patch("/me")
@jwt_required()
def update_me():
    """Update the display name shown next to the user's messages."""
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}

    if "display_name" in data:
        display_name = (data.get("display_name") or "").strip()[:80]
        user.display_name = display_name or None

    db.session.commit()
    return jsonify(
        id=user.id,
        username=user.username,
        student_id=user.student_id,
        display_name=user.display_name,
    )


@bp.delete("/me")
@jwt_required()
def delete_me():
    """Delete the account, its chats and its messages.

    A personal account carries no shared state that has to be kept: the
    messages go with it, and the other members simply see the chat shrink.
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)

    # Remove the membership rows first so the cascade does not have to guess.
    conversation_ids = [
        row.conversation_id
        for row in Member.query.filter_by(user_id=uid).all()
    ]
    Message.query.filter(Message.sender_id == uid).delete(synchronize_session=False)
    Member.query.filter_by(user_id=uid).delete(synchronize_session=False)
    SavedMessage.query.filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.commit()

    # Groups the user was the last admin of lose their admin; a member is
    # promoted so the group is not left without one.
    for conversation_id in conversation_ids:
        conv = db.session.get(Conversation, conversation_id)
        if conv is None:
            continue
        remaining = Member.query.filter_by(conversation_id=conversation_id).all()
        if remaining and not any(m.role == "admin" for m in remaining):
            remaining[0].role = "admin"
        db.session.commit()

    # `conversation.created_by` points at the user, so it is cleared before the
    # row goes. The chat itself stays, with whoever else is still in it.
    Conversation.query.filter_by(created_by=uid).update(
        {"created_by": None}, synchronize_session=False
    )
    db.session.commit()

    db.session.delete(user)
    db.session.commit()

    # The account's live sockets must not keep receiving anything.
    from .chats import leave_user_from_room

    for conversation_id in conversation_ids:
        leave_user_from_room(uid, conversation_id)

    return jsonify(ok=True)


@bp.get("/users/search")
@jwt_required()
def search_users():
    """Find people so the frontend can start a chat with them.

    Chats display usernames only, but a chat is started with a student ID, so
    the search results carry both. An empty query returns an empty list
    rather than everybody's details.
    """
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify([])
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 50)
    except ValueError:
        raise ChatError("limit must be a number") from None

    # Match on username, display name or student ID, case-insensitively.
    pattern = f"%{query}%"
    users = (
        User.query.filter(
            db.or_(
                db.func.lower(User.username).like(pattern.lower()),
                db.func.lower(db.func.coalesce(User.display_name, "")).like(
                    pattern.lower()
                ),
                db.func.lower(User.student_id).like(pattern.lower()),
            )
        )
        .order_by(User.username)
        .limit(limit)
        .all()
    )
    return jsonify(
        [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "student_id": u.student_id,
            }
            for u in users
        ]
    )
