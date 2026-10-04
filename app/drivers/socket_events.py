import logging

from flask import request
from flask_socketio import emit, join_room

from app.extensions import socketio
from .stream import build_driver_request_queue


log = logging.getLogger("rideshare.driver_socket")


def emit_driver_queue(driver_id, sid=None):
    payload = {
        "driver_id": int(driver_id),
        "requests": build_driver_request_queue(
            int(driver_id)
        ),
    }

    if sid:
        socketio.emit(
            "driver_request_queue",
            payload,
            to=sid,
        )
    else:
        socketio.emit(
            "driver_request_queue",
            payload,
            room=f"driver:{int(driver_id)}",
        )

    log.info(
        "[DRIVER QUEUE PUSH] driver=%s count=%s target=%s",
        driver_id,
        len(payload["requests"]),
        sid or f"driver:{int(driver_id)}",
    )

    return payload


@socketio.on("register_driver")
def register_driver(data):
    from app.trips.models import Trip
    from app.trips.stream import build_trip_snapshot

    driver_id = int(data["driver_id"])
    driver_room = f"driver:{driver_id}"

    join_room(driver_room)
    from .models import Driver
    from .routes import serialize_driver
    from app.extensions import db
    driver = db.session.get(Driver, driver_id)
    if driver is not None:
        emit("driver_availability", serialize_driver(driver))

    active_trip = (
        Trip.query
        .filter(
            Trip.driver_id == driver_id,
            Trip.status.in_(
                [
                    "DRIVER_ASSIGNED",
                    "DRIVER_EN_ROUTE",
                    "DRIVER_ARRIVED",
                    "PICKUP_PENDING",
                    "IN_PROGRESS",
                ]
            ),
        )
        .order_by(Trip.accepted_at.desc())
        .first()
    )

    log.info(
        "[DRIVER REGISTER] sid=%s driver=%s room=%s active_trip=%s",
        request.sid,
        driver_id,
        driver_room,
        active_trip.id if active_trip else None,
    )

    emit(
        "connection_lifecycle",
        {
            "phase": "DRIVER_REGISTERED",
            "driver_id": driver_id,
            "active_trip_id": (
                active_trip.id
                if active_trip else None
            ),
        },
    )

    emit_driver_queue(
        driver_id,
        sid=request.sid,
    )

    if active_trip is None:
        return

    trip_room = f"trip:{active_trip.id}"
    join_room(trip_room)

    snapshot = build_trip_snapshot(
        active_trip.id
    )

    log.info(
        "[DRIVER AUTO JOIN] sid=%s driver=%s trip=%s state=%s",
        request.sid,
        driver_id,
        active_trip.id,
        snapshot["status"],
    )

    emit(
        "trip_lifecycle",
        {
            "trip_id": active_trip.id,
            "phase": "JOINED",
            "role": "DRIVER",
            "actor_id": driver_id,
            "status": snapshot["status"],
            "reason": "ACTIVE_TRIP_RECOVERY",
        },
    )

    emit(
        "trip_snapshot",
        {
            "reason": "ACTIVE_TRIP_RECOVERY",
            "snapshot": snapshot,
        },
    )


@socketio.on("request_driver_queue")
def request_driver_queue(data):
    driver_id = int(data["driver_id"])

    log.info(
        "[DRIVER QUEUE REQUEST] sid=%s driver=%s",
        request.sid,
        driver_id,
    )

    emit_driver_queue(
        driver_id,
        sid=request.sid,
    )
