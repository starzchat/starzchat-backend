import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///starzchat.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Messages vanish after this many seconds unless a user saves them.
    DEFAULT_MESSAGE_TTL = int(os.getenv("DEFAULT_MESSAGE_TTL", "86400"))
    CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "60"))
    MAX_MESSAGE_LENGTH = 2000
    RUN_SCHEDULER = True

    # --- Rate limiting -----------------------------------------------------
    # Requests per window, per client IP. The limits are deliberately strict
    # on login (brute force) and looser on sending (a chatty user is normal).
    RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
    RATE_LIMIT_REGISTER = os.getenv("RATE_LIMIT_REGISTER", "5/hour")
    RATE_LIMIT_SEND = os.getenv("RATE_LIMIT_SEND", "30/minute")
    RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
    # Where the counters live. Use Redis in a multi-worker deployment so the
    # limits are shared instead of per-process.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"

    # --- Schema management ------------------------------------------------
    # When true the app creates any missing tables on startup (development
    # convenience). When false the schema is owned by Alembic migrations, so
    # set this to false in production and run `flask db upgrade` instead.
    AUTO_CREATE_SCHEMA = os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true"

    # --- Frontend integration -------------------------------------------
    # Origins allowed to call the API from a browser. Use "*" in development;
    # list your real frontend URLs (comma separated) in production.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    # Socket.IO client origins (comma separated, or "*" for any).
    SOCKETIO_CORS_ORIGINS = os.getenv("SOCKETIO_CORS_ORIGINS", "*")
    # Serve the bundled demo UI in app/static. Set to false when the frontend
    # is a separate app; the API keeps working either way.
    SERVE_FRONTEND = os.getenv("SERVE_FRONTEND", "true").lower() == "true"
    # Public base URL of this API, used by the frontend and reported by /api/docs.
    API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5000")

    # Student IDs are upper-cased before this pattern is checked. Adjust to
    # match Starz University's real ID format.
    STUDENT_ID_PATTERN = os.getenv("STUDENT_ID_PATTERN", r"^[A-Z0-9-]{3,20}$")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RUN_SCHEDULER = False
    # Tests build their schema directly, so they never need the migrations.
    AUTO_CREATE_SCHEMA = True
