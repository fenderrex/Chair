import math
import os
from app.extensions import db


class DispatchSettings(db.Model):
    __tablename__ = "dispatch_settings"
    id = db.Column(db.Integer, primary_key=True)
    initial_radius_miles = db.Column(db.Float, nullable=False, default=3.0)
    radius_miles = db.Column(db.Float, nullable=False)
    max_radius_miles = db.Column(db.Float, nullable=False, default=25.0)
    expansion_seconds = db.Column(db.Float, nullable=False)
    response_seconds = db.Column(db.Integer, nullable=False)
    last_driver_wait_seconds = db.Column(db.Integer, nullable=False, default=30)
    fare_multiplier = db.Column(db.Float, nullable=False, default=1.25)


def get_dispatch_settings():
    settings = db.session.get(DispatchSettings, 1)

    return {
        "initial_radius_miles": (
            settings.initial_radius_miles
            if settings
            else float(os.getenv("DISPATCH_INITIAL_RADIUS_MILES", "3"))
        ),
        "radius_miles": (
            settings.radius_miles
            if settings
            else float(os.getenv("DISPATCH_RADIUS_MILES", "5"))
        ),
        "max_radius_miles": (
            settings.max_radius_miles
            if settings
            else float(os.getenv("DISPATCH_MAX_RADIUS_MILES", "25"))
        ),
        "expansion_seconds": (
            settings.expansion_seconds
            if settings
            else float(os.getenv("DISPATCH_EXPANSION_SECONDS", "20"))
        ),
        "response_seconds": (
            settings.response_seconds
            if settings
            else int(os.getenv("OFFER_RESPONSE_SECONDS", "20"))
        ),
        "last_driver_wait_seconds": (
            settings.last_driver_wait_seconds
            if settings
            else int(os.getenv("LAST_DRIVER_WAIT_SECONDS", "30"))
        ),
        "fare_multiplier": (
            settings.fare_multiplier
            if settings
            else float(os.getenv("FARE_ESCALATION_MULTIPLIER", "1.25"))
        ),
    }


def save_dispatch_settings(data):
    specs = [
        ("initial_radius_miles", .1, 1000, False),
        ("radius_miles", .1, 100, False),
        ("max_radius_miles", .1, 1000, False),
        ("expansion_seconds", 0, 3600, False),
        ("response_seconds", 5, 3600, True),
        ("last_driver_wait_seconds", 5, 3600, True),
        ("fare_multiplier", 1.01, 10, False),
    ]

    current = get_dispatch_settings()
    values = {}

    for name, low, high, whole in specs:
        raw = data.get(name, current[name])

        if isinstance(raw, bool):
            raise ValueError(f"Invalid {name}")

        try:
            value = float(raw)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid {name}")

        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be between {low} and {high}")

        if whole and not value.is_integer():
            raise ValueError(f"{name} must be a whole number")

        values[name] = int(value) if whole else value

    if values["max_radius_miles"] < values["initial_radius_miles"]:
        raise ValueError("max_radius_miles must be greater than or equal to initial_radius_miles")

    settings = db.session.get(DispatchSettings, 1)

    if settings is None:
        settings = DispatchSettings(id=1)
        db.session.add(settings)

    for key, value in values.items():
        setattr(settings, key, value)

    db.session.commit()
    return get_dispatch_settings()


def distance_fraction(distance, nearest, farthest):
    if farthest <= nearest:
        return 0.0
    return max(0.0, min(1.0, (distance - nearest) / (farthest - nearest)))
