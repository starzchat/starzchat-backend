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


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RUN_SCHEDULER = False
