from datetime import datetime, timezone
from app.extensions import db
from .models import LocationUpdate


def save_location_update(
    trip_id,
    actor_type,
    latitude,
    longitude,
    accuracy=None,
    altitude=None,
    heading=None,
    speed=None,
    recorded_at=None,
):
    record = LocationUpdate(
        trip_id=trip_id,
        actor_type=actor_type,
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
        altitude=altitude,
        heading=heading,
        speed=speed,
        recorded_at=recorded_at,
        received_at=datetime.now(timezone.utc),
    )
    db.session.add(record)
    db.session.commit()
    return record
