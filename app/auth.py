import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from .extensions import db
from .models import User

bp = Blueprint("auth", __name__, url_prefix="/api")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


@bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not USERNAME_RE.match(username):
        return jsonify(error="Username must be 3-32 letters, numbers or _"), 400
    if len(password) < 8:
        return jsonify(error="Password must be at least 8 characters"), 400
    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        return jsonify(error="Username already taken"), 409

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify(token=token, username=user.username), 201


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    user = User.query.filter(
        db.func.lower(User.username) == (data.get("username") or "").lower()
    ).first()
    if user is None or not user.check_password(data.get("password") or ""):
        return jsonify(error="Invalid username or password"), 401
    token = create_access_token(identity=str(user.id))
    return jsonify(token=token, username=user.username)


@bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    return jsonify(id=user.id, username=user.username)
