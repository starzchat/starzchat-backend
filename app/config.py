import os
from datetime import timedelta


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

    # Student IDs are upper-cased before this pattern is checked. Adjust to
    # match Starz University's real ID format.
    STUDENT_ID_PATTERN = os.getenv("STUDENT_ID_PATTERN", r"^[A-Z0-9-]{3,20}$")
    # When true, only IDs imported with `flask import-roster` can register.
    REQUIRE_ROSTER = os.getenv("REQUIRE_ROSTER", "false").lower() == "true"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RUN_SCHEDULER = False
    REQUIRE_ROSTER = False
