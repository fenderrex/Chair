from datetime import timedelta

from app.extensions import db
from app.trips.models import Trip, RideOffer
from app.trips.state import REQUESTED
from app.drivers.services import available_drivers_ranked
from .timing import utcnow
from .fare import estimate_pickup_eta_seconds
from .queue import _refresh_trip_dispatch_summary


def build_dispatch_plan(trip_id):
    trip = (
        Trip.query
        .filter_by(id=trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        return []

    existing = (
        RideOffer.query
        .filter_by(trip_id=trip.id)
        .order_by(
            RideOffer.distance_miles.asc(),
            RideOffer.rank.asc(),
        )
        .all()
    )

    if existing:
        return existing

    from app.admin.settings import get_dispatch_settings

    settings = get_dispatch_settings()

    initial_radius = max(
        0.0,
        float(settings.get("initial_radius_miles", 3.0)),
    )

    radius_step = max(
        0.001,
        float(settings["radius_miles"]),
    )

    timer_seconds = max(
        0.001,
        float(settings["expansion_seconds"]),
    )

    max_radius = max(
        initial_radius,
        float(settings["max_radius_miles"]),
    )

    ranked = available_drivers_ranked(
        trip.pickup_latitude,
        trip.pickup_longitude,
    )

    print(
        "[PASSENGER SEARCH PLAN] "
        f"trip={trip.id} "
        f"initial_radius={initial_radius:.3f}mi "
        f"radius_step={radius_step:.3f}mi "
        f"timer={timer_seconds:.2f}s "
        f"max_radius={max_radius:.3f}mi "
        f"candidates={len(ranked)}",
        flush=True,
    )

    start_time = utcnow()
    trip.dispatch_started_at = start_time
    trip.no_driver_admin_notified_at = None
    trip.fare_wait_until = None
    trip.next_dispatch_at = (
        start_time
        + timedelta(seconds=timer_seconds)
    )

    if not ranked:
        trip.status = REQUESTED
        db.session.commit()

        print(
            "[PASSENGER SEARCH PLAN EMPTY] "
            f"trip={trip.id}",
            flush=True,
        )

        return []

    offers = []

    for index, item in enumerate(
        ranked,
        start=1,
    ):
        distance = float(
            item["distance_miles"]
        )

        if distance <= initial_radius:
            interval_number = 0
        else:
            interval_number = max(
                1,
                int(
                    __import__("math").ceil(
                        (distance - initial_radius)
                        / radius_step
                    )
                ),
            )

        within_max_radius = distance <= max_radius
        inside_initial_radius = (
            within_max_radius
            and distance <= initial_radius
        )

        eligible_at = (
            start_time
            + timedelta(
                seconds=(
                    timer_seconds
                    * interval_number
                )
            )
        )

        eta = estimate_pickup_eta_seconds(
            distance
        )

        offer = RideOffer(
            trip_id=trip.id,
            driver_id=item["driver"].id,
            rank=index,
            distance_miles=distance,
            pickup_eta_seconds=eta,
            distance_fraction=(
                distance / radius_step
            ),
            response_seconds=None,
            dispatch_score=distance,
            eligible_at=eligible_at,
            status=(
                "OFFERED"
                if inside_initial_radius
                else "WAITING"
                if within_max_radius
                else "CLOSED"
            ),
            offered_at=(
                start_time
                if inside_initial_radius
                else None
            ),
            expires_at=None,
            closed_at=(
                None
                if within_max_radius
                else start_time
            ),
        )

        db.session.add(offer)
        offers.append(offer)

        print(
            "[PASSENGER SEARCH DRIVER] "
            f"trip={trip.id} "
            f"rank={index} "
            f"driver={item['driver'].id} "
            f"distance={distance:.3f}mi "
            f"initial_radius={initial_radius:.3f}mi "
        f"radius_step={radius_step:.3f}mi "
            f"interval={interval_number} "
            f"eligible_at={eligible_at.isoformat() if eligible_at else None} "
            f"status={offer.status}",
            flush=True,
        )

    db.session.flush()
    _refresh_trip_dispatch_summary(
        trip
    )
    db.session.commit()

    return offers
