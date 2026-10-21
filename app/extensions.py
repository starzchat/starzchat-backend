from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
# The API is consumed by a separate frontend app, so CORS is enabled.
cors = CORS()
# "threading" keeps setup simple (no eventlet/gevent). Switch for production scale.
socketio = SocketIO(async_mode="threading", cors_allowed_origins="*")
