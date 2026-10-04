from flask import Blueprint, jsonify, request

from app.extensions import db, socketio
from app.maps.services import get_route_estimate
from .models import Trip
from .stream import build_trip_snapshot, publish_trip_snapshot
from .timing import iso_utc
from .services import (
    accept_trip_offer,
    active_requests,
    calculate_fare_estimate,
    cancel_trip,
    create_trip_request,
    get_active_trip_for_passenger,
    decline_trip_offer,
    driver_mark_arrived,
    driver_claim_pickup,
    passenger_confirm_pickup,
    passenger_request_pickup_help,
    accept_fare_escalation,
    decline_fare_escalation,
    serialize_trip_request,
)

bp = Blueprint("trips", __name__)


@bp.post("/estimate")
def estimate_trip():
    data = request.get_json(force=True)

    route = get_route_estimate(
        float(data["pickup_lat"]),
        float(data["pickup_lng"]),
        float(data["destination_lat"]),
        float(data["destination_lng"]),
    )

    return jsonify({
        "route": route,
        "fare": calculate_fare_estimate(route),
    })


@bp.post("/request")
def request_trip():
    data = request.get_json(force=True)

    passenger_id = data.get("passenger_id")
    passenger_name = data.get(
        "passenger_name",
        "Demo Passenger",
    )

    # Serialize request creation for a real passenger account. A second
    # simultaneous request waits for this row lock, then sees the first trip.
    if passenger_id is not None:
        from app.users.models import User

        (
            User.query
            .filter_by(id=int(passenger_id))
            .with_for_update()
            .first()
        )

    existing_trip = get_active_trip_for_passenger(
        passenger_id=passenger_id,
        passenger_name=passenger_name,
    )

    if existing_trip is not None:
        return jsonify({
            "error": "Passenger already has an active ride request",
            "code": "ACTIVE_TRIP_EXISTS",
            "active_trip_id": existing_trip.id,
            "status": existing_trip.status,
        }), 409

    route = get_route_estimate(
        float(data["pickup_lat"]),
        float(data["pickup_lng"]),
        float(data["destination_lat"]),
        float(data["destination_lng"]),
    )

    try:
        trip, fare, _ = create_trip_request(
            data,
            route,
        )
    except ValueError as exc:
        existing_trip = get_active_trip_for_passenger(
            passenger_id=passenger_id,
            passenger_name=passenger_name,
        )

        return jsonify({
            "error": str(exc),
            "code": "ACTIVE_TRIP_EXISTS",
            "active_trip_id": (
                existing_trip.id
                if existing_trip
                else None
            ),
            "status": (
                existing_trip.status
                if existing_trip
                else None
            ),
        }), 409

    from app.trips.notices import (
        record_passenger_notice,
    )

    record_passenger_notice(
        trip.id,
        "RIDE_REQUESTED",
        "Ride requested. The collision/match lane is checking nearby drivers.",
        emit=True,
    )

    publish_trip_snapshot(
        trip.id,
        reason="TRIP_REQUESTED",
    )

    return jsonify({
        "trip": serialize_trip_request(trip),
        "route": route,
        "fare": fare,
        "dispatch": {
            "status": trip.status.lower(),
            "wave": trip.dispatch_wave,
            "next_dispatch_at": (
                trip.next_dispatch_at.isoformat()
                if trip.next_dispatch_at else None
            ),
        },
    })


@bp.get("/requests/active")
def active_trip_requests():
    driver_id = request.args.get(
        "driver_id",
        type=int,
    )

    if driver_id is not None:
        from app.drivers.stream import build_driver_request_queue
        return jsonify(build_driver_request_queue(driver_id))
    return jsonify([serialize_trip_request(trip) for trip in active_requests()])



@bp.post("/<int:trip_id>/accept")
def accept_trip(trip_id):
    data = request.get_json(force=True)

    try:
        trip, driver = accept_trip_offer(
            trip_id,
            int(data["driver_id"]),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    # Accepting a ride prepares the pickup route but does not move the
    # vehicle. Movement begins only when the driver presses Start Driving.
    try:
        from app.broker.services import (
            create_or_reset_job,
            serialize_job,
        )

        simulation_job, _ = (
            create_or_reset_job(
                trip.id,
                driver.id,
            )
        )

        simulation_payload = (
            serialize_job(
                simulation_job
            )
        )

    except ValueError as exc:
        simulation_payload = {
            "status": "PREPARE_FAILED",
            "error": str(exc),
        }

    from app.trips.notices import (
        record_passenger_notice,
    )

    record_passenger_notice(
        trip.id,
        "DRIVER_ACCEPTED",
        f"{driver.display_name} accepted your ride. Search matching is now closed for this trip.",
        payload={
            "driver_id": driver.id,
        },
        emit=True,
    )

    publish_trip_snapshot(
        trip.id,
        reason="DRIVER_ACCEPTED_ROUTE_READY",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
        "driver_id": driver.id,
        "driver_name": driver.display_name,
        "offer_rank": trip.offer_rank,
        "simulation": simulation_payload,
    })


@bp.post("/<int:trip_id>/decline")
def decline_trip(trip_id):
    data = request.get_json(force=True)

    try:
        trip = decline_trip_offer(
            trip_id,
            int(data["driver_id"]),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    publish_trip_snapshot(
        trip.id,
        reason="DRIVER_DECLINED",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
    })


@bp.get("/<int:trip_id>")
def trip_detail(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    driver_id = request.args.get(
        "driver_id",
        type=int,
    )

    return jsonify(
        serialize_trip_request(
            trip,
            driver_id=driver_id,
        )
        | {
            "id": trip.id,
            "driver_id": trip.driver_id,
        }
    )


@bp.post("/<int:trip_id>/fare-escalation/accept")
def accept_fare_increase(trip_id):
    data = request.get_json(
        silent=True
    ) or {}

    try:
        trip = accept_fare_escalation(
            trip_id,
            passenger_id=data.get(
                "passenger_id"
            ),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    from app.dispatch.events import (
        publish_proximity_event,
    )

    publish_proximity_event(
        trip.id,
        reason="PASSENGER_ACCEPTED_FARE_ESCALATION",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
        "estimated_fare": trip.estimated_fare,
        "fare_round": trip.fare_round,
    })


@bp.post("/<int:trip_id>/fare-escalation/decline")
def decline_fare_increase(trip_id):
    data = request.get_json(
        silent=True
    ) or {}

    try:
        trip = decline_fare_escalation(
            trip_id,
            passenger_id=data.get(
                "passenger_id"
            ),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    publish_trip_snapshot(
        trip.id,
        reason="PASSENGER_DECLINED_FARE_ESCALATION",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
    })


@bp.post("/<int:trip_id>/arrive")
def driver_arrive(trip_id):
    data = request.get_json(force=True)

    try:
        trip, newly_arrived = driver_mark_arrived(
            trip_id,
            int(data["driver_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    if newly_arrived:
        from app.trips.notices import (
            record_passenger_notice,
        )

        record_passenger_notice(
            trip.id,
            "DRIVER_ARRIVED",
            "Your driver marked that they arrived at the pickup point. Your pickup waiting timer has started.",
            payload={
                "driver_id": trip.driver_id,
                "driver_arrived_at": iso_utc(trip.driver_arrived_at),
            },
            emit=True,
        )

        publish_trip_snapshot(
            trip.id,
            reason="DRIVER_MARKED_ARRIVED",
        )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
        "driver_arrived_at": iso_utc(trip.driver_arrived_at),
    })


@bp.post("/<int:trip_id>/pickup-claim")
def pickup_claim(trip_id):
    data = request.get_json(force=True)

    try:
        trip = driver_claim_pickup(
            trip_id,
            int(data["driver_id"]),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    from app.trips.notices import (
        record_passenger_notice,
    )

    record_passenger_notice(
        trip.id,
        "PICKUP_CONFIRMATION_REQUIRED",
        "Your driver marked pickup. Confirm only after you are in the vehicle.",
        emit=True,
    )

    publish_trip_snapshot(
        trip.id,
        reason="DRIVER_CLAIMED_PICKUP",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
        "cancel_locked": True,
    })


@bp.post("/<int:trip_id>/pickup-help")
def pickup_help(trip_id):
    data = request.get_json(
        silent=True
    ) or {}

    try:
        trip = passenger_request_pickup_help(
            trip_id,
            passenger_id=data.get(
                "passenger_id"
            ),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    publish_trip_snapshot(
        trip.id,
        reason="PASSENGER_REQUESTED_PICKUP_HELP",
    )

    alert = {
        "trip_id": trip.id,
        "passenger_id": trip.passenger_id,
        "passenger_name": trip.passenger_name,
        "driver_id": trip.driver_id,
        "message": (
            "Passenger requested help during pickup confirmation."
        ),
        "created_at": (
            trip.pickup_help_requested_at.isoformat()
            if trip.pickup_help_requested_at
            else None
        ),
    }

    socketio.emit(
        "admin_pickup_help_alert",
        alert,
        room="admin:live",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
        "pickup_help_requested": True,
        "pickup_help_requested_at": (
            trip.pickup_help_requested_at.isoformat()
            if trip.pickup_help_requested_at
            else None
        ),
    })


@bp.post("/<int:trip_id>/pickup-confirm")
def pickup_confirm(trip_id):
    data = request.get_json(
        silent=True
    ) or {}

    try:
        trip = passenger_confirm_pickup(
            trip_id,
            passenger_id=data.get(
                "passenger_id"
            ),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    from app.trips.notices import (
        record_passenger_notice,
    )

    record_passenger_notice(
        trip.id,
        "PICKUP_CONFIRMED",
        "Pickup confirmed. The driver may now continue to the drop-off.",
        emit=True,
    )

    publish_trip_snapshot(
        trip.id,
        reason="PASSENGER_CONFIRMED_PICKUP",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
        "cancel_locked": True,
    })


@bp.post("/<int:trip_id>/cancel")
def cancel_trip_route(trip_id):
    data = request.get_json(
        silent=True,
    ) or {}

    try:
        trip = cancel_trip(
            trip_id,
            passenger_id=data.get(
                "passenger_id"
            ),
            passenger_name=data.get(
                "passenger_name"
            ),
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    publish_trip_snapshot(
        trip.id,
        reason="PASSENGER_CANCELED",
    )

    return jsonify({
        "ok": True,
        "trip_id": trip.id,
        "status": trip.status,
    })


@bp.get("/passenger/<int:passenger_id>/active")
def passenger_active_trip(passenger_id):
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

    if trip is None:
        return jsonify({
            "active": False,
        })

    return jsonify({
        "active": True,
        "trip_id": trip.id,
        "status": trip.status,
    })


@bp.get("/<int:trip_id>/live")
def trip_live_state(trip_id):
    snapshot = build_trip_snapshot(
        trip_id
    )

    if snapshot is None:
        return jsonify({
            "error": "Trip not found",
        }), 404

    return jsonify(snapshot)


@bp.post("/internal/stream-publish")
@bp.post("/internal/stream-publish")
def internal_stream_publish():
    """
    Local-only bridge used by the broker subprocess.

    Broker changes are already committed to MySQL before this endpoint is
    called. This route only publishes the authoritative persisted state.
    """
    import logging

    from app.dispatch.events import (
        publish_proximity_event,
    )

    log = logging.getLogger(
        "rideshare.trip_socket"
    )

    if request.remote_addr not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        log.warning(
            "[BROKER CALLBACK REJECTED] remote=%s",
            request.remote_addr,
        )

        return jsonify({
            "error":
                "Local broker callback only",
        }), 403

    data = request.get_json(
        force=True
    )

    trip_id = int(
        data["trip_id"]
    )

    reason = str(
        data.get(
            "reason",
            "BROKER_UPDATE",
        )
    )

    new_driver_ids = [
        int(driver_id)
        for driver_id in (
            data.get(
                "new_driver_ids",
                [],
            )
            or []
        )
    ]

    notices = (
        data.get(
            "notices",
            [],
        )
        or []
    )

    from app.trips.notices import (
        record_passenger_notice,
    )

    for notice in notices:
        message = str(
            notice.get(
                "message",
                "",
            )
        ).strip()

        if not message:
            continue

        record_passenger_notice(
            trip_id,
            notice.get(
                "kind",
                "BROKER_STEP",
            ),
            message,
            payload=
                notice.get(
                    "payload",
                    {},
                ),
            emit=True,
        )

    snapshot = (
        publish_proximity_event(
            trip_id,
            reason=reason,
            new_driver_ids=
                new_driver_ids,
        )
    )

    if snapshot is None:
        return jsonify({
            "ok": False,
            "missing": True,
        }), 404

    return jsonify({
        "ok": True,
        "trip_id": trip_id,
        "status":
            snapshot["status"],
    })
