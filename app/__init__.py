import csv
import os
import sys

import click
from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt, limiter, migrate, socketio
from .services import ChatError


def _running_migration_command():
    """True when the process is a `flask db ...` CLI call.

    Alembic compares the models against the live database to work out what
    changed. If the app had already created the missing tables on startup,
    that comparison would always come back empty and every generated
    migration would be empty. So schema creation is skipped for these calls.

    The command is checked anywhere in the arguments, because it is invoked
    as `flask --app run db migrate`, where "db" is not the first argument.
    """
    return "db" in sys.argv[1:]


def _enable_sqlite_foreign_keys(app):
    """Make SQLite enforce foreign keys, like Postgres does.

    SQLite ignores foreign keys unless they are switched on for every
    connection. Without this, a test can pass on SQLite and then fail on the
    production database, so the pragma is turned on wherever SQLite is used.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return

    @event.listens_for(Engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Import sockets first so its event handlers are registered before init_app.
    from . import api_docs, auth, chats, sockets  # noqa: F401
    from .cleanup import delete_expired_messages, start_scheduler
    from .models import AllowedStudent
    from .services import normalize_id

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    limiter.init_app(app)
    # A default limit on every route; the sensitive ones below are stricter.
    limiter.default_limits = [app.config["RATE_LIMIT_DEFAULT"]]
    _enable_sqlite_foreign_keys(app)
    socketio.init_app(
        app, cors_allowed_origins=app.config["SOCKETIO_CORS_ORIGINS"]
    )

    app.register_blueprint(auth.bp)
    app.register_blueprint(chats.bp)
    app.register_blueprint(api_docs.bp)

    # ChatError is raised from several blueprints, so the handler is registered
    # on the app: a blueprint-level handler would not catch the others' errors.
    @app.errorhandler(ChatError)
    def handle_chat_error(err):
        return jsonify(error=err.message), err.status

    # A JWT is only accepted while it matches the user's current token
    # version. Logging out or changing the password bumps that version, which
    # invalidates every token issued before it.
    @jwt.token_in_blocklist_loader
    def token_is_revoked(_header, payload):
        from .sockets import token_is_current

        user_id = payload.get("sub")
        if user_id is None:
            return True
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return True
        return not token_is_current(user_id, payload.get("ver"))

    @app.get("/")
    def index():
        """Serve the bundled demo UI, if enabled.

        The frontend is optional: the API under /api works regardless, so the
        UI can live in its own app and point at this server.
        """
        if not app.config["SERVE_FRONTEND"]:
            return jsonify(
                name="StarzChat API",
                status="ok",
                docs="/api/docs",
            )
        return app.send_static_file("index.html")

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.cli.command("cleanup")
    def cleanup_command():
        """Delete expired messages now."""
        print(f"Deleted {delete_expired_messages()} expired messages")

    @app.cli.command("import-roster")
    @click.argument("csv_path")
    def import_roster(csv_path):
        """Load valid student IDs from a CSV with columns student_id,full_name."""
        count = 0
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                student_id = normalize_id(row.get("student_id"))
                if not student_id:
                    continue
                student = db.session.get(AllowedStudent, student_id)
                if student is None:
                    student = AllowedStudent(student_id=student_id)
                    db.session.add(student)
                student.full_name = (row.get("full_name") or "").strip()
                count += 1
        db.session.commit()
        print(f"Imported {count} students into the roster")

    @app.cli.command("reset-db")
    def reset_db():
        """DANGER: drop and recreate every table (development only)."""
        if click.confirm("This deletes ALL data. Continue?"):
            db.drop_all()
            db.create_all()
            print("Database reset")

    if app.config["AUTO_CREATE_SCHEMA"] and not _running_migration_command():
        with app.app_context():
            db.create_all()  # dev convenience; production uses `flask db upgrade`

    # Only start the scheduler in the real server process (not the reloader parent).
    if app.config["RUN_SCHEDULER"] and (
        not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        start_scheduler(app)

    return app
