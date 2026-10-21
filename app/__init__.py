import csv
import os

import click
from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt, migrate, socketio


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
    socketio.init_app(
        app, cors_allowed_origins=app.config["SOCKETIO_CORS_ORIGINS"]
    )

    app.register_blueprint(auth.bp)
    app.register_blueprint(chats.bp)
    app.register_blueprint(api_docs.bp)

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

    with app.app_context():
        db.create_all()  # fine for an MVP; switch to `flask db migrate` later

    # Only start the scheduler in the real server process (not the reloader parent).
    if app.config["RUN_SCHEDULER"] and (
        not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        start_scheduler(app)

    return app
