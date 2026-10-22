from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
# The API is consumed by a separate frontend app, so CORS is enabled.
cors = CORS()
# Rate limiting protects login from brute force and stops message flooding.
# Storage is in-process by default; swap in Redis for a multi-worker setup.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    strategy="fixed-window",
)
# "threading" keeps setup simple (no eventlet/gevent). Switch for production scale.
socketio = SocketIO(async_mode="threading", cors_allowed_origins="*")
