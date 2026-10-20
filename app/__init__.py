import os

from dotenv import load_dotenv
from flask import Flask, jsonify

from .config import Config
from .extensions import db, jwt, migrate, socketio


def create_app(config_object=Config):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Import sockets first so its event handlers are registered before init_app.
    from . import auth, chats, sockets  # noqa: F401
    from .cleanup import delete_expired_messages, start_scheduler

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    socketio.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(chats.bp)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.cli.command("cleanup")
    def cleanup_command():
        """Delete expired messages now."""
        print(f"Deleted {delete_expired_messages()} expired messages")

    with app.app_context():
        db.create_all()  # fine for an MVP; switch to `flask db migrate` later

    # Only start the scheduler in the real server process (not the reloader parent).
    if app.config["RUN_SCHEDULER"] and (
        not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        start_scheduler(app)

    return app
