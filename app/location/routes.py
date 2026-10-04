from flask import Blueprint, jsonify, request

from app.extensions import socketio
from .services import save_location_update

bp = Blueprint("location", __name__)


@bp.post("/update")
def update_location():
    data = request.get_json(force=True)

    trip_id = int(data["trip_id"])
    actor_type = data["actor_type"]
    latitude = float(data["latitude"])
    longitude = float(data["longitude"])
    driver_id = data.get("driver_id")

    record = save_location_update(
        trip_id=trip_id,
        actor_type=actor_type,
        latitude=latitude,
        longitude=longitude,
        accuracy=data.get("accuracy"),
        altitude=data.get("altitude"),
        heading=data.get("heading"),
        speed=data.get("speed"),
    )

    if actor_type == "driver" and driver_id is not None:
        from app.location.providers.gps import (
            submit_gps_driver_location,
        )

        submit_gps_driver_location(
            int(driver_id),
            latitude,
            longitude,
        )

    payload = {
        "trip_id": record.trip_id,
        "actor_type": record.actor_type,
        "driver_id": int(driver_id) if driver_id is not None else None,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "heading": record.heading,
        "speed": record.speed,
        "received_at": record.received_at.isoformat(),
    }

    socketio.emit("location_update", payload)

    if driver_id is not None:
        socketio.emit(
            "driver_location",
            payload,
            room=f"driver:{int(driver_id)}",
        )

    from app.admin.platform_map import publish_platform_map
    publish_platform_map()
    return jsonify({
        "ok": True,
        "location_id": record.id,
    })
