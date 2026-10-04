import logging

from flask import request
from flask_socketio import emit, join_room, leave_room

from app.extensions import socketio
from .stream import build_trip_snapshot


log = logging.getLogger("rideshare.trip_socket")


def trip_room(trip_id):
    return f"trip:{int(trip_id)}"


@socketio.on("connect")
def socket_connected(auth=None):
    log.info(
        "[SOCKET CONNECT] sid=%s remote=%s auth=%s",
        request.sid,
        request.remote_addr,
        bool(auth),
    )

    emit(
        "connection_lifecycle",
        {
            "phase": "CONNECTED",
            "sid": request.sid,
            "message": "WebSocket connection established",
        },
    )


@socketio.on("join_trip")
def join_trip(data):
    trip_id = int(data["trip_id"])
    role = str(data.get("role", "UNKNOWN")).upper()
    actor_id = data.get("actor_id")

    snapshot = build_trip_snapshot(trip_id)

    if snapshot is None:
        log.warning(
            "[TRIP JOIN REJECTED] sid=%s trip=%s role=%s actor=%s reason=trip_not_found",
            request.sid,
            trip_id,
            role,
            actor_id,
        )

        emit(
            "trip_lifecycle",
            {
                "trip_id": trip_id,
                "phase": "JOIN_REJECTED",
                "reason": "Trip not found",
            },
        )
        return

    room = trip_room(trip_id)
    join_room(room)

    log.info(
        "[TRIP JOIN] sid=%s room=%s trip=%s role=%s actor=%s state=%s",
        request.sid,
        room,
        trip_id,
        role,
        actor_id,
        snapshot["status"],
    )

    emit(
        "trip_lifecycle",
        {
            "trip_id": trip_id,
            "phase": "JOINED",
            "role": role,
            "actor_id": actor_id,
            "status": snapshot["status"],
        },
    )

    emit(
        "trip_snapshot",
        {
            "reason": "JOIN_SNAPSHOT",
            "snapshot": snapshot,
        },
    )




@socketio.on("register_passenger")
def register_passenger(data):
    from .models import Trip

    passenger_id = int(data["passenger_id"])

    active_states = [
        "REQUESTED",
        "OFFERED",
        "DRIVER_ASSIGNED",
        "DRIVER_EN_ROUTE",
        "DRIVER_ARRIVED",
        "PICKUP_PENDING",
        "IN_PROGRESS",
    ]

    trip = (
        Trip.query
        .filter(
            Trip.passenger_id == passenger_id,
            Trip.status.in_(active_states),
        )
        .order_by(Trip.created_at.desc())
        .first()
    )

    log.info(
        "[PASSENGER REGISTER] sid=%s passenger=%s active_trip=%s",
        request.sid,
        passenger_id,
        trip.id if trip else None,
    )

    emit(
        "connection_lifecycle",
        {
            "phase": "PASSENGER_REGISTERED",
            "passenger_id": passenger_id,
            "active_trip_id": (
                trip.id if trip else None
            ),
        },
    )

    if trip is None:
        return

    room = trip_room(trip.id)
    join_room(room)

    snapshot = build_trip_snapshot(
        trip.id
    )

    log.info(
        "[PASSENGER AUTO JOIN] sid=%s passenger=%s trip=%s state=%s",
        request.sid,
        passenger_id,
        trip.id,
        snapshot["status"],
    )

    emit(
        "trip_lifecycle",
        {
            "trip_id": trip.id,
            "phase": "JOINED",
            "role": "PASSENGER",
            "actor_id": passenger_id,
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


@socketio.on("leave_trip")
def leave_trip(data):
    trip_id = int(data["trip_id"])
    reason = str(data.get("reason", "CLIENT_LEAVE"))
    room = trip_room(trip_id)

    leave_room(room)

    log.info(
        "[TRIP LEAVE] sid=%s room=%s trip=%s reason=%s",
        request.sid,
        room,
        trip_id,
        reason,
    )

    emit(
        "trip_lifecycle",
        {
            "trip_id": trip_id,
            "phase": "LEFT",
            "reason": reason,
        },
    )


@socketio.on("disconnect")
def socket_disconnected(reason):
    log.info(
        "[SOCKET DISCONNECT] sid=%s remote=%s reason=%s",
        request.sid,
        request.remote_addr,
        reason,
    )
