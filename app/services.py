from flask import current_app

from .extensions import db
from .models import Conversation, Member, Message, message_expiry


def normalize_id(value):
    """Student IDs are compared case-insensitively and stored upper-case."""
    return (value or "").strip().upper()


class ChatError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def get_membership(conversation_id, user_id):
    return Member.query.filter_by(
        conversation_id=conversation_id, user_id=user_id
    ).first()


def require_member(conversation_id, user_id):
    """Every read/write goes through this, so outsiders can't see a chat."""
    member = get_membership(conversation_id, user_id)
    if member is None:
        raise ChatError("Conversation not found", 404)
    return member


def create_message(conversation_id, user_id, body):
    body = (body or "").strip()
    if not body:
        raise ChatError("Message cannot be empty")
    if len(body) > current_app.config["MAX_MESSAGE_LENGTH"]:
        raise ChatError("Message too long")

    require_member(conversation_id, user_id)
    conversation = db.session.get(Conversation, conversation_id)
    message = Message(
        conversation_id=conversation_id,
        sender_id=user_id,
        body=body,
        expires_at=message_expiry(
            conversation, current_app.config["DEFAULT_MESSAGE_TTL"]
        ),
    )
    db.session.add(message)
    db.session.commit()
    return message
