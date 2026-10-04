import atexit
import logging
import os
import subprocess
import sys

from app import create_app
from app.extensions import socketio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

logging.getLogger("rideshare.trip_socket").setLevel(logging.INFO)
logging.getLogger("rideshare.trip_stream").setLevel(logging.INFO)
logging.getLogger("rideshare.driver_socket").setLevel(logging.INFO)
logging.getLogger("rideshare.broker_routes").setLevel(logging.INFO)

app = create_app(start_broker=True)
broker_process = None


def log_socket_runtime():
    import importlib.metadata

    packages = [
        "Flask-SocketIO",
        "python-socketio",
        "python-engineio",
        "simple-websocket",
        "gevent",
    ]

    versions = {}

    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "MISSING"

    print(
        "[SOCKET SERVER] "
        f"async_mode={socketio.async_mode} "
        f"host=127.0.0.1 port=5100",
        flush=True,
    )

    for package, version in versions.items():
        print(
            f"[SOCKET SERVER] {package}={version}",
            flush=True,
        )

    # Inspect the selected driver without importing optional backends.
    engine = socketio.server.eio
    websocket = engine._async.get("websocket")
    backend = (
        f"{websocket.__module__}.{websocket.__qualname__}"
        if websocket is not None else "unavailable"
    )
    print(
        f"[SOCKET SERVER] websocket_backend={backend} "
        f"python={sys.version.split()[0]}",
        flush=True,
    )


def start_broker():
    global broker_process
    if os.getenv("BROKER_PROCESS") == "1":
        return
    broker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "broker.py")
    broker_process = subprocess.Popen(
        [sys.executable, broker_path],
        cwd=os.path.dirname(broker_path),
    )
    print(f"[APP] simulation broker PID {broker_process.pid}", flush=True)

def stop_broker():
    global broker_process
    if broker_process is None:
        return
    if broker_process.poll() is None:
        broker_process.terminate()
        try:
            broker_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            broker_process.kill()
    broker_process = None

if __name__ == "__main__":
    log_socket_runtime()
    start_broker()
    atexit.register(stop_broker)
    socketio.run(
        app,
        host="127.0.0.1",
        port=5100,
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
