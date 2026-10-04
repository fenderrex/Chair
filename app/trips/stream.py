import logging
from datetime import datetime, timezone

from app.extensions import db, socketio
from app.drivers.models import Driver
from app.drivers.services import haversine_miles
from app.dispatch.fare import estimate_pickup_eta_seconds
from app.broker.models import SimulationJob
from app.surveys.models import RideSurvey

from .models import RideOffer, Trip, FareEscalation
from .services import seconds_until
from .timing import iso_utc, trip_timing


log = logging.getLogger("rideshare.trip_stream")


TERMINAL_TRIP_STATES = {
    "COMPLETED",
    "CANCELED",
}


def _pickup_wait_seconds(trip):
    if trip.driver_arrived_at is None:
        return 0

    now = datetime.now(timezone.utc)
    arrived_at = trip.driver_arrived_at

    if arrived_at.tzinfo is None:
        now = now.replace(tzinfo=None)

    return max(
        0,
        int((now - arrived_at).total_seconds()),
    )


def build_trip_snapshot(trip_id):
    trip = db.session.get(Trip, int(trip_id))

    if trip is None:
        return None

    driver = (
        db.session.get(Driver, trip.driver_id)
        if trip.driver_id is not None
        else None
    )

    vehicle = (
        driver.vehicles[0]
        if driver and driver.vehicles
        else None
    )

    live_driver_distance_miles = None
    live_driver_eta_seconds = trip.driver_eta_seconds

    if (
        driver is not None
        and driver.current_latitude is not None
        and driver.current_longitude is not None
        and trip.status in {
            "DRIVER_ASSIGNED",
            "DRIVER_EN_ROUTE",
            "DRIVER_ARRIVED",
        }
    ):
        live_driver_distance_miles = haversine_miles(
            float(trip.pickup_latitude),
            float(trip.pickup_longitude),
            float(driver.current_latitude),
            float(driver.current_longitude),
        )
        live_driver_eta_seconds = (
            0
            if trip.status == "DRIVER_ARRIVED"
            else estimate_pickup_eta_seconds(live_driver_distance_miles)
        )

    job = SimulationJob.query.filter_by(
        trip_id=trip.id
    ).first()

    open_offers = (
        RideOffer.query
        .filter_by(
            trip_id=trip.id,
            status="OFFERED",
        )
        .order_by(RideOffer.rank.asc())
        .all()
    )

    reviewing_drivers = []

    for offer in open_offers:
        reviewing_driver = db.session.get(
            Driver,
            offer.driver_id,
        )

        if reviewing_driver is None:
            continue

        live_review_distance = (
            haversine_miles(
                float(trip.pickup_latitude),
                float(trip.pickup_longitude),
                float(reviewing_driver.current_latitude),
                float(reviewing_driver.current_longitude),
            )
            if reviewing_driver.current_latitude is not None
            and reviewing_driver.current_longitude is not None
            else float(offer.distance_miles or 0.0)
        )

        reviewing_drivers.append({
            "driver_id":
                reviewing_driver.id,
            "name":
                reviewing_driver.display_name,
            "distance_miles":
                round(live_review_distance, 2),
            "pickup_eta_seconds":
                estimate_pickup_eta_seconds(live_review_distance),
            "offered_at": (
                offer.offered_at.isoformat()
                if offer.offered_at
                else None
            ),
            "fare":
                float(
                    trip.estimated_fare
                ),
        })

    waiting_offers = (
        RideOffer.query
        .filter_by(
            trip_id=trip.id,
            status="WAITING",
        )
        .order_by(
            RideOffer.eligible_at.asc(),
            RideOffer.rank.asc(),
        )
        .all()
    )

    from .services import current_dispatch_expansion
    from app.admin.settings import get_dispatch_settings

    survey_roles = {
        str(row[0]).upper()
        for row in (
            db.session.query(
                RideSurvey.role
            )
            .filter(
                RideSurvey.trip_id
                == trip.id
            )
            .all()
        )
    }

    dispatch_clock = current_dispatch_expansion(
        trip,
        get_dispatch_settings(),
    )

    from .notices import recent_trip_notices

    recent_notices = recent_trip_notices(
        trip.id,
        limit=20,
    )

    return {
        "trip_id": trip.id,
        "timing": trip_timing(trip),
        "status": trip.status,
        "terminal": trip.status in TERMINAL_TRIP_STATES,
        "notice_sequence": int(
            trip.notice_sequence or 0
        ),
        "recent_notices": recent_notices,
        "passenger_id": trip.passenger_id,
        "passenger_name": trip.passenger_name,
        "pickup": {
            "latitude": trip.pickup_latitude,
            "longitude": trip.pickup_longitude,
        },
        "passenger_location": {
            "latitude": (
                trip.passenger_current_latitude
                if trip.passenger_current_latitude
                is not None
                else trip.pickup_latitude
            ),
            "longitude": (
                trip.passenger_current_longitude
                if trip.passenger_current_longitude
                is not None
                else trip.pickup_longitude
            ),
        },
        "destination": {
            "latitude": trip.destination_latitude,
            "longitude": trip.destination_longitude,
        },
        "route_geometry": __import__("json").loads(
            trip.route_geometry_json
        ),
        "estimated_fare": trip.estimated_fare,
        "original_estimated_fare": (
            trip.original_estimated_fare
            if trip.original_estimated_fare is not None
            else trip.estimated_fare
        ),
        "fare_multiplier": trip.fare_multiplier,
        "fare_round": trip.fare_round,
        "fare_wait_until": (
            trip.fare_wait_until.isoformat()
            if trip.fare_wait_until
            else None
        ),
        "fare_review_pending": bool(
            trip.fare_review_pending
        ),
        "no_driver_admin_notified_at": (
            trip.no_driver_admin_notified_at.isoformat()
            if trip.no_driver_admin_notified_at
            else None
        ),
        "estimated_distance_meters": trip.estimated_distance_meters,
        "estimated_duration_seconds": trip.estimated_duration_seconds,
        "route_provider": trip.route_provider,
        "progress_percent": float(
            trip.progress_percent or 0.0
        ),
        "driver_distance_miles": (
            round(live_driver_distance_miles, 2)
            if live_driver_distance_miles is not None
            else None
        ),
        "driver_eta_seconds": live_driver_eta_seconds,
        "driver_arrived_at": iso_utc(trip.driver_arrived_at),
        "pickup_wait_seconds": _pickup_wait_seconds(trip),
        "pickup_claimed_at": iso_utc(trip.pickup_claimed_at),
        "pickup_confirmed_at": iso_utc(trip.pickup_confirmed_at),
        "pickup_help_requested_at": (
            trip.pickup_help_requested_at.isoformat()
            if trip.pickup_help_requested_at
            else None
        ),
        "cancel_locked": bool(
            trip.cancel_locked_at is not None
            or trip.status in {
                "PICKUP_PENDING",
                "IN_PROGRESS",
                "COMPLETED",
            }
        ),

        "fare_escalation": (
            lambda item: {
                "round_number": item.round_number,
                "original_fare": item.original_fare,
                "multiplier": item.multiplier,
                "offered_fare": item.offered_fare,
                "status": item.status,
                "prompted_at": (
                    item.prompted_at.isoformat()
                    if item.prompted_at
                    else None
                ),
            } if item else None
        )(
            FareEscalation.query
            .filter_by(
                trip_id=trip.id,
                status="PENDING",
            )
            .order_by(
                FareEscalation.round_number.desc()
            )
            .first()
        ),

        "dispatch": {
            "wave": trip.dispatch_wave,
            "elapsed_seconds": (
                dispatch_clock["elapsed_seconds"]
            ),
            "remaining_seconds": (
                dispatch_clock["remaining_seconds"]
            ),
            "expansion_fraction": (
                dispatch_clock["expansion_fraction"]
            ),
            "search_radius_miles": (
                dispatch_clock["search_radius_miles"]
            ),
            "radius_step_miles": (
                dispatch_clock["radius_step_miles"]
            ),
            "radius_paused": (
                dispatch_clock["radius_paused"]
            ),
            "radius_capped": (
                dispatch_clock["radius_capped"]
            ),
            "max_search_radius_miles": (
                dispatch_clock["max_radius_miles"]
            ),
            "open_offer_count": len(open_offers),
            "waiting_offer_count": len(waiting_offers),
            "reviewing_drivers":
                reviewing_drivers,
            "next_dispatch_at": (
                trip.next_dispatch_at.isoformat()
                if trip.next_dispatch_at
                else None
            ),
            "seconds_until_expand": (
                seconds_until(trip.next_dispatch_at)
                if trip.next_dispatch_at
                else None
            ),
        },

        "surveys": {
            "passenger_submitted":
                "PASSENGER"
                in survey_roles,
            "driver_submitted":
                "DRIVER"
                in survey_roles,
        },

        "driver": {
            "id": driver.id,
            "name": driver.display_name,
            "latitude": driver.current_latitude,
            "longitude": driver.current_longitude,
            "last_location_at": (
                driver.last_location_at.isoformat()
                if driver.last_location_at
                else None
            ),
            "vehicle": {
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "color": vehicle.color,
                "plate": vehicle.plate,
                "plate_state": vehicle.plate_state,
            } if vehicle else None,
        } if driver else None,

        "simulation": {
            "status": job.status,
            "phase": job.phase,
            "current_index": job.current_index,
            "progress_percent": job.progress_percent,
            "next_due_at": (
                job.next_due_at.isoformat()
                if job.next_due_at
                else None
            ),
            "route_geometry": (
                __import__("json").loads(
                    job.route_geometry_json
                )
                if job.route_geometry_json
                else None
            ),
        } if job else None,
    }



def publish_trip_snapshot(trip_id, reason="STATE_CHANGE"):
    snapshot = build_trip_snapshot(trip_id)

    if snapshot is None:
        log.warning(
            "[TRIP STREAM PUBLISH SKIP] trip=%s reason=%s result=missing",
            trip_id,
            reason,
        )
        return None

    room = f"trip:{int(trip_id)}"

    log.info(
        "[TRIP STREAM PUBLISH] room=%s trip=%s reason=%s state=%s progress=%.1f eta=%s terminal=%s",
        room,
        trip_id,
        reason,
        snapshot["status"],
        snapshot["progress_percent"],
        snapshot["driver_eta_seconds"],
        snapshot["terminal"],
    )

    socketio.emit(
        "trip_snapshot",
        {
            "reason": reason,
            "snapshot": snapshot,
        },
        room=room,
    )

    socketio.emit(
        "trip_lifecycle",
        {
            "trip_id": int(trip_id),
            "phase": "STATE_UPDATE",
            "reason": reason,
            "status": snapshot["status"],
        },
        room=room,
    )

    if snapshot["terminal"]:
        socketio.emit(
            "trip_lifecycle",
            {
                "trip_id": int(trip_id),
                "phase": "TERMINAL",
                "reason": reason,
                "status": snapshot["status"],
            },
            room=room,
        )

    from app.admin.live import publish_admin_trip
    publish_admin_trip(trip_id)
    return snapshot
