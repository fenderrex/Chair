from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO


db = SQLAlchemy()

# Auto-detect an installed backend; gevent is optional.
# With requirements.txt alone, threading uses simple-websocket for WebSockets.
socketio = SocketIO(
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
    ping_interval=25,
    ping_timeout=20,
    transports=["websocket"],
)
