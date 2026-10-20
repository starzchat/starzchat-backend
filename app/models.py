from datetime import UTC, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    # Stored naive in UTC so SQLite and Postgres behave the same.
    return datetime.now(UTC).replace(tzinfo=None)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80))
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AllowedStudent(db.Model):
    """Optional roster of valid student IDs, imported from the university's list."""

    student_id = db.Column(db.String(20), primary_key=True)
    full_name = db.Column(db.String(80))


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False)  # "direct" or "group"
    name = db.Column(db.String(80))  # groups only
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    # Per-chat expiry override in seconds. NULL means use the app default.
    ttl_seconds = db.Column(db.Integer)

    members = db.relationship(
        "Member", backref="conversation", cascade="all, delete-orphan"
    )


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversation.id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    role = db.Column(db.String(10), default="member", nullable=False)  # admin/member
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("conversation_id", "user_id", name="uq_member"),
    )


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversation.id"), nullable=False, index=True
    )
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    # Indexed so the cleanup job's "expires_at < now" scan stays fast.
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    sender = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender": self.sender.username,
            "body": self.body,
            "created_at": self.created_at.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z",
        }


class SavedMessage(db.Model):
    """A per-user copy of a message. It survives after the original expires."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    conversation_id = db.Column(db.Integer, nullable=False)
    sender_username = db.Column(db.String(32), nullable=False)
    body = db.Column(db.Text, nullable=False)
    original_created_at = db.Column(db.DateTime, nullable=False)
    saved_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender": self.sender_username,
            "body": self.body,
            "original_created_at": self.original_created_at.isoformat() + "Z",
            "saved_at": self.saved_at.isoformat() + "Z",
        }


def message_expiry(conversation, default_ttl):
    ttl = conversation.ttl_seconds or default_ttl
    return utcnow() + timedelta(seconds=ttl)
