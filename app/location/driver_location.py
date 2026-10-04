from datetime import datetime, timezone

from app.extensions import db, socketio
from app.drivers.models import Driver


def set_driver_location(
    driver_id,
    latitude,
    longitude,
    *,
    source="unknown",
    emit=True,
):
    """
    Common driver-location write path for demo and production.

    Providers must stop here. Dispatch behavior is handled by the same
    proximity service regardless of where the coordinates came from.
    """
    driver = (
        Driver.query
        .filter_by(id=int(driver_id))
        .populate_existing()
        .first()
    )

    if driver is None:
        return None

    driver.current_latitude = float(latitude)
    driver.current_longitude = float(longitude)
    driver.last_location_at = datetime.now(timezone.utc)

    db.session.commit()

    if emit:
        payload = {
            "driver_id": driver.id,
            "driver_name": driver.display_name,
            "latitude": driver.current_latitude,
            "longitude": driver.current_longitude,
            "recorded_at": driver.last_location_at.isoformat(),
            "source": source,
        }

        socketio.emit(
            "driver_location",
            payload,
            room=f"driver:{driver.id}",
        )

        socketio.emit(
            "admin_driver_location",
            payload,
        )

    from app.admin.platform_map import publish_platform_map
    publish_platform_map()

    return driver
