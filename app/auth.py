import re

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from .extensions import db
from .models import AllowedStudent, User
from .services import normalize_id

bp = Blueprint("auth", __name__, url_prefix="/api")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def find_by_username(username):
    return User.query.filter(
        db.func.lower(User.username) == (username or "").strip().lower()
    ).first()


@bp.post("/auth/register")
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

    if current_app.config["REQUIRE_ROSTER"]:
        roster_entry = db.session.get(AllowedStudent, student_id)
        if roster_entry is None:
            return jsonify(error="This student ID is not on the university roster"), 403
        # The official name from the roster wins over whatever was typed.
        display_name = roster_entry.full_name or display_name

    user = User(
        student_id=student_id, username=username, display_name=display_name or None
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify(token=token, username=user.username), 201


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    user = find_by_username(data.get("username"))
    if user is None or not user.check_password(data.get("password") or ""):
        # Same message for both cases, so usernames can't be probed through login.
        return jsonify(error="Invalid username or password"), 401
    token = create_access_token(identity=str(user.id))
    return jsonify(token=token, username=user.username)


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
