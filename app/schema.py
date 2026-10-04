from sqlalchemy import inspect, text

from app.extensions import db


DRIVER_COLUMNS = {
    "current_latitude": "FLOAT NULL",
    "current_longitude": "FLOAT NULL",
    "last_location_at": "DATETIME NULL",
    "fare_increase_accept_count": "INT NOT NULL DEFAULT 0",
    "last_fare_increase_accept_at": "DATETIME NULL",
}

RIDE_OFFER_COLUMNS = {
    "distance_fraction": "FLOAT NULL",
    "response_seconds": "INT NULL",
    "expires_at": "DATETIME NULL",
    "pickup_eta_seconds": "INT NOT NULL DEFAULT 0",
    "eligible_at": "DATETIME NULL",
}


DISPATCH_SETTINGS_COLUMNS = {
    "initial_radius_miles": "FLOAT NOT NULL DEFAULT 3",
    "max_radius_miles": "FLOAT NOT NULL DEFAULT 25",
    "last_driver_wait_seconds": "INT NOT NULL DEFAULT 30",
    "fare_multiplier": "FLOAT NOT NULL DEFAULT 1.25",
}


TRIP_COLUMNS = {
    "original_estimated_fare": "FLOAT NULL",
    "fare_multiplier": "FLOAT NOT NULL DEFAULT 1.25",
    "fare_round": "INT NOT NULL DEFAULT 0",
    "fare_wait_until": "DATETIME NULL",
    "fare_review_pending": "BOOLEAN NOT NULL DEFAULT 0",
    "no_driver_admin_notified_at": "DATETIME NULL",

    "driver_arrived_at": "DATETIME NULL",
    "pickup_claimed_at": "DATETIME NULL",
    "pickup_confirmed_at": "DATETIME NULL",
    "pickup_help_requested_at": "DATETIME NULL",
    "cancel_locked_at": "DATETIME NULL",
    "dispatch_wave": "INT NOT NULL DEFAULT 0",
    "next_dispatch_at": "DATETIME NULL",
    "dispatch_started_at": "DATETIME NULL",
    "passenger_id": "INT NULL",
    "progress_percent": "FLOAT NOT NULL DEFAULT 0",
    "driver_eta_seconds": "INT NULL",
    "canceled_at": "DATETIME NULL",
    "offered_driver_id": "INT NULL",
    "offered_at": "DATETIME NULL",
    "offer_rank": "INT NULL",
    "passenger_current_latitude": "FLOAT NULL",
    "passenger_current_longitude": "FLOAT NULL",
    "collision_dirty": "BOOLEAN NOT NULL DEFAULT 0",
    "collision_reason": "VARCHAR(80) NULL",
    "collision_requested_at": "DATETIME NULL",
    "collision_revision": "INT NOT NULL DEFAULT 0",
    "notice_sequence": "INT NOT NULL DEFAULT 0",
}

SIMULATION_JOB_COLUMNS = {
    "phase": "VARCHAR(30) NOT NULL DEFAULT 'TO_PICKUP'",
    "next_due_at": "DATETIME NULL",
}


def _column_names(table_name):
    inspector = inspect(db.engine)
    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def _ensure_columns(table_name, required_columns):
    inspector = inspect(db.engine)

    if table_name not in inspector.get_table_names():
        return

    existing = _column_names(table_name)

    for column_name, sql_type in required_columns.items():
        if column_name in existing:
            continue

        db.session.execute(
            text(
                f"ALTER TABLE `{table_name}` "
                f"ADD COLUMN `{column_name}` {sql_type}"
            )
        )

    db.session.commit()


def ensure_schema_updates():
    _ensure_columns("drivers", DRIVER_COLUMNS)
    _ensure_columns("trips", TRIP_COLUMNS)
    _ensure_columns("ride_offers", RIDE_OFFER_COLUMNS)
    _ensure_columns("dispatch_settings", DISPATCH_SETTINGS_COLUMNS)
    _ensure_columns("simulation_jobs", SIMULATION_JOB_COLUMNS)
