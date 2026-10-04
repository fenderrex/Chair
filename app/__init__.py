import os
from urllib.parse import quote_plus

from flask import Flask
from dotenv import load_dotenv

from .extensions import db, socketio


# Default MySQL configuration.
# These defaults match the working database settings supplied for this project.
# Environment variables can still override them later.
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "history_db")


def build_database_uri():
    password = quote_plus(DB_PASSWORD)

    return (
        f"mysql+pymysql://{DB_USER}:{password}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )


def create_app(start_broker=True):
    load_dotenv()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.config["SECRET_KEY"] = os.getenv(
        "SECRET_KEY",
        "dev-secret-change-me",
    )

    # Use the explicit MySQL configuration above instead of DATABASE_URL.
    # This prevents an empty or stale DATABASE_URL from overriding DB_PASSWORD.
    app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    app.config["OSRM_BASE_URL"] = os.getenv(
        "OSRM_BASE_URL",
        "https://router.project-osrm.org",
    )
    app.config["DEMO_MODE"] = os.getenv("DEMO_MODE", "1") == "1"

    db.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
    )

    from .drivers import socket_events
    from .trips import socket_events as trip_socket_events

    from .home.routes import bp as home_bp
    from .auth.routes import bp as auth_bp
    from .users.routes import bp as users_bp
    from .messages.routes import bp as messages_bp
    from .drivers.routes import bp as drivers_bp
    from .trips.routes import bp as trips_bp
    from .location.routes import bp as location_bp
    from .maps.routes import bp as maps_bp
    from .payments.routes import bp as payments_bp
    from .id_processing.routes import bp as id_processing_bp
    from .admin.routes import bp as admin_bp
    from .admin import live
    from .broker.routes import bp as broker_bp
    from .surveys.routes import bp as surveys_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp, url_prefix="/users")
    app.register_blueprint(messages_bp, url_prefix="/messages")
    app.register_blueprint(drivers_bp, url_prefix="/drivers")
    app.register_blueprint(trips_bp, url_prefix="/trips")
    app.register_blueprint(location_bp, url_prefix="/location")
    app.register_blueprint(maps_bp, url_prefix="/maps")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(id_processing_bp, url_prefix="/id-processing")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(broker_bp, url_prefix="/broker")
    app.register_blueprint(surveys_bp, url_prefix="/surveys")

    with app.app_context():
        db.create_all()

        # db.create_all() creates missing tables but does not alter existing ones.
        # Apply the small development schema upgrades needed by newer app versions
        # before any ORM query references the new columns.
        from .schema import ensure_schema_updates
        ensure_schema_updates()

        from .users.services import ensure_demo_users

        ensure_demo_users()

        if app.config.get("DEMO_MODE"):
            from .drivers.services import ensure_test_drivers

            demo_drivers = ensure_test_drivers()

            print(
                "[DEMO DRIVERS READY] "
                + ", ".join(
                    (
                        f"id={driver.id} "
                        f"name={driver.display_name} "
                        f"online={driver.is_online} "
                        f"available={driver.is_available}"
                    )
                    for driver in demo_drivers
                ),
                flush=True,
            )

    return app
