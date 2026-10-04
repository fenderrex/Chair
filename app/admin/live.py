from flask_socketio import emit, join_room
from app.extensions import db, socketio
from app.trips.models import Trip, RideOffer
from app.drivers.models import Driver
from app.trips.timing import trip_timing, iso_utc


def admin_trip(trip):
    from app.trips.services import current_dispatch_expansion
    from app.admin.settings import get_dispatch_settings

    dispatch_clock = current_dispatch_expansion(
        trip,
        get_dispatch_settings(),
    )

    offers = (
        RideOffer.query
        .filter_by(trip_id=trip.id)
        .order_by(RideOffer.rank)
        .all()
    )

    offer_counts = {
        state: sum(
            1 for offer in offers
            if offer.status == state
        )
        for state in (
            "OFFERED",
            "WAITING",
            "DECLINED",
            "CLOSED",
        )
    }

    return {
        "trip_id": trip.id,
        "status": trip.status,
        "timing": trip_timing(trip),
        "original_estimated_fare": (
            trip.original_estimated_fare
            if trip.original_estimated_fare is not None
            else trip.estimated_fare
        ),
        "estimated_fare": trip.estimated_fare,
        "fare_round": trip.fare_round,
        "fare_multiplier": trip.fare_multiplier,
        "fare_wait_until": iso_utc(trip.fare_wait_until),
        "fare_review_pending": bool(trip.fare_review_pending),
        "pickup_help_requested_at": (
            iso_utc(trip.pickup_help_requested_at)
        ),
        "dispatch_elapsed_seconds": (
            dispatch_clock["elapsed_seconds"]
        ),
        "dispatch_remaining_seconds": (
            dispatch_clock["remaining_seconds"]
        ),
        "dispatch_expansion_fraction": (
            dispatch_clock["expansion_fraction"]
        ),
        "search_radius_miles": (
            dispatch_clock["search_radius_miles"]
        ),
        "initial_search_radius_miles": (
            dispatch_clock["initial_radius_miles"]
        ),
        "search_radius_step_miles": (
            dispatch_clock["radius_step_miles"]
        ),
        "max_search_radius_miles": (
            dispatch_clock["max_radius_miles"]
        ),
        "search_radius_capped": (
            dispatch_clock["radius_capped"]
        ),
        "search_radius_paused": (
            dispatch_clock["radius_paused"]
        ),
        "offered_driver_count": offer_counts["OFFERED"],
        "waiting_driver_count": offer_counts["WAITING"],
        "declined_driver_count": offer_counts["DECLINED"],
        "closed_driver_count": offer_counts["CLOSED"],
        "no_driver_admin_notified_at": (
            iso_utc(trip.no_driver_admin_notified_at)
        ),
        "offers": [{"driver_id": o.driver_id, "name": (db.session.get(Driver, o.driver_id).display_name
                         if db.session.get(Driver, o.driver_id) else "Deleted driver"),
                        "status": o.status, "distance_miles": o.distance_miles,
                        "distance_fraction": o.distance_fraction, "eligible_at": iso_utc(o.eligible_at),
                        "expires_at": iso_utc(o.expires_at)}
                       for o in offers],
    }


@socketio.on("register_admin")
def register_admin(data=None):
    join_room("admin:live")
    from .platform_map import platform_snapshot
    emit("admin_platform_map", platform_snapshot())
    emit("admin_snapshot", {"trips": [admin_trip(t) for t in Trip.query.order_by(Trip.id.desc()).limit(100).all()]})


def publish_admin_trip(trip_id):
    from .platform_map import publish_platform_map
    publish_platform_map()
    trip = db.session.get(Trip, trip_id)
    socketio.emit("admin_trip_update", admin_trip(trip) if trip else {"trip_id": trip_id, "deleted": True}, room="admin:live")
