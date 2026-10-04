import math
from datetime import timedelta

from app.extensions import db
from app.trips.models import Trip, RideOffer
from app.trips.state import REQUESTED, OFFERED
from app.drivers.services import haversine_miles
from .timing import utcnow
from .radius import current_dispatch_expansion
from .fare import estimate_pickup_eta_seconds
from .queue import _refresh_trip_dispatch_summary


def activate_due_offers(trip_id):
    """
    PIPELINE 03 — AUTHORITATIVE LIVE QUEUE RECONCILIATION

    The drivers table is the source of truth for current location.

    Every broker tick this function:
        1. reads fresh Driver rows from MySQL
        2. computes current pickup distance from current latitude/longitude
        3. decides live queue membership from distance <= current search radius
        4. overwrites RideOffer.distance_miles every pass
        5. removes drivers that leave the radius
        6. adds drivers that enter the radius
        7. rewrites queue rank by current distance

    No request-time distance is trusted for live membership.
    """
    trip = (
        Trip.query
        .filter_by(id=trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        return []

    if trip.status not in {
        REQUESTED,
        OFFERED,
    }:
        return []

    from app.drivers.models import Driver
    from app.drivers.services import haversine_miles
    from app.admin.settings import get_dispatch_settings

    settings = get_dispatch_settings()
    now = utcnow()
    changed = []

    clock = current_dispatch_expansion(
        trip,
        settings,
        now=now,
    )

    search_radius = float(
        clock["search_radius_miles"]
    )

    radius_step = max(
        0.001,
        float(clock["radius_step_miles"]),
    )

    initial_radius = max(
        0.0,
        float(clock.get("initial_radius_miles", 0.0)),
    )

    max_radius = max(
        initial_radius,
        float(clock["max_radius_miles"]),
    )

    timer_seconds = max(
        0.001,
        float(settings["expansion_seconds"]),
    )

    # Drivers assigned to another active trip are not candidates.
    busy_driver_ids = {
        int(row[0])
        for row in (
            db.session.query(Trip.driver_id)
            .filter(
                Trip.driver_id.is_not(None),
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
            .all()
        )
    }

    # populate_existing forces SQLAlchemy to refresh rows from MySQL rather
    # than reusing identity-map values left over from a previous broker tick.
    drivers = (
        Driver.query
        .filter(
            Driver.is_online.is_(True),
            Driver.verification_status
            == "APPROVED",
        )
        .order_by(Driver.id.asc())
        .populate_existing()
        .all()
    )

    existing_offers = {
        int(offer.driver_id): offer
        for offer in (
            RideOffer.query
            .filter_by(trip_id=trip.id)
            .populate_existing()
            .all()
        )
    }

    live_driver_ids = set()
    inside_driver_ids = set()

    for driver in drivers:
        driver_id = int(driver.id)

        if driver_id in busy_driver_ids:
            continue

        if (
            driver.current_latitude is None
            or driver.current_longitude is None
        ):
            continue

        # Repair stale availability from actual trip assignment state.
        if not bool(driver.is_available):
            driver.is_available = True

        live_driver_ids.add(driver_id)

        distance = haversine_miles(
            float(trip.pickup_latitude),
            float(trip.pickup_longitude),
            float(driver.current_latitude),
            float(driver.current_longitude),
        )

        within_max_radius = (
            distance <= max_radius
        )

        inside_radius = (
            within_max_radius
            and distance <= search_radius
        )

        if inside_radius:
            inside_driver_ids.add(
                driver_id
            )

        if distance <= initial_radius:
            interval_number = 0
        else:
            interval_number = max(
                1,
                int(
                    math.ceil(
                        (distance - initial_radius)
                        / radius_step
                    )
                ),
            )

        eligible_at = (
            trip.dispatch_started_at
            + timedelta(
                seconds=(
                    interval_number
                    * timer_seconds
                )
            )
            if trip.dispatch_started_at
            else now
        )

        offer = existing_offers.get(
            driver_id
        )

        if offer is None:
            offer = RideOffer(
                trip_id=trip.id,
                driver_id=driver_id,
                rank=999999,
                distance_miles=distance,
                pickup_eta_seconds=
                    estimate_pickup_eta_seconds(
                        distance
                    ),
                distance_fraction=(
                    distance / radius_step
                ),
                response_seconds=None,
                dispatch_score=distance,
                eligible_at=eligible_at,
                status=(
                    "WAITING"
                    if within_max_radius
                    else "CLOSED"
                ),
                offered_at=None,
                expires_at=None,
                closed_at=(
                    None
                    if within_max_radius
                    else now
                ),
            )

            db.session.add(offer)
            db.session.flush()

            existing_offers[
                driver_id
            ] = offer

            changed.append(offer)

            print(
                "[LIVE QUEUE DRIVER DISCOVERED] "
                f"trip={trip.id} "
                f"driver={driver_id}",
                flush=True,
            )

        # Explicit decline survives movement for this fare round.
        if offer.status == "DECLINED":
            # Keep distance fresh even for declined rows so admin/debug values
            # still reflect reality.
            offer.distance_miles = distance
            offer.pickup_eta_seconds = (
                estimate_pickup_eta_seconds(
                    distance
                )
            )
            offer.distance_fraction = (
                distance / radius_step
            )
            offer.dispatch_score = distance
            continue

        previous_status = offer.status
        offer._previous_status = previous_status

        previous_distance = float(
            offer.distance_miles
            if offer.distance_miles is not None
            else distance
        )

        # ALWAYS overwrite distance from the driver's current DB location.
        offer.distance_miles = distance
        offer.pickup_eta_seconds = (
            estimate_pickup_eta_seconds(
                distance
            )
        )
        offer.distance_fraction = (
            distance / radius_step
        )
        offer.dispatch_score = distance
        offer.expires_at = None

        if not within_max_radius:
            offer.status = "CLOSED"
            offer.closed_at = now
            offer.eligible_at = eligible_at

            if previous_status in {"OFFERED", "WAITING"}:
                offer._left_offer_this_tick = True
                offer._removed_from_search_tick = True

            if (
                previous_status != offer.status
                or abs(previous_distance - distance) > 0.000001
            ):
                changed.append(offer)

            continue

        if inside_radius:
            offer.status = "OFFERED"
            offer.closed_at = None
            offer.eligible_at = now

            if previous_status != "OFFERED":
                offer.offered_at = now
                offer._became_offered_this_tick = True

                print(
                    "[LIVE QUEUE ENTER] "
                    f"trip={trip.id} "
                    f"driver={driver_id} "
                    f"distance={distance:.3f}mi "
                    f"radius={search_radius:.3f}mi",
                    flush=True,
                )

        else:
            offer.status = "WAITING"
            offer.closed_at = None
            offer.eligible_at = eligible_at

            if previous_status == "OFFERED":
                offer._left_offer_this_tick = True

                print(
                    "[LIVE QUEUE LEAVE] "
                    f"trip={trip.id} "
                    f"driver={driver_id} "
                    f"distance={distance:.3f}mi "
                    f"radius={search_radius:.3f}mi",
                    flush=True,
                )

        if (
            previous_status != offer.status
            or abs(
                previous_distance - distance
            ) > 0.000001
        ):
            changed.append(offer)

            print(
                "[LIVE QUEUE DISTANCE] "
                f"trip={trip.id} "
                f"driver={driver_id} "
                f"lat={float(driver.current_latitude):.6f} "
                f"lng={float(driver.current_longitude):.6f} "
                f"distance={distance:.3f}mi "
                f"status={offer.status}",
                flush=True,
            )

    # Drivers no longer online/approved/location-valid/busy are removed from
    # this passenger's active queue.
    for driver_id, offer in existing_offers.items():
        if offer.status == "DECLINED":
            continue

        if driver_id not in live_driver_ids:
            if offer.status in {
                "OFFERED",
                "WAITING",
                "EXPIRED",
            }:
                old_status = offer.status
                offer.status = "CLOSED"
                offer.closed_at = now
                offer.expires_at = None
                offer._previous_status = old_status
                offer._removed_from_search_tick = True
                changed.append(offer)

                print(
                    "[LIVE QUEUE REMOVE DRIVER] "
                    f"trip={trip.id} "
                    f"driver={driver_id} "
                    f"old_status={old_status}",
                    flush=True,
                )

    # Rebuild OFFERED queue rank strictly by current pickup distance.
    offered = [
        offer
        for offer in existing_offers.values()
        if offer.status == "OFFERED"
    ]

    offered.sort(
        key=lambda offer: (
            float(offer.distance_miles),
            int(offer.driver_id),
        )
    )

    for rank, offer in enumerate(
        offered,
        start=1,
    ):
        if int(offer.rank) != rank:
            offer.rank = rank
            changed.append(offer)

    # WAITING rows are ranked after OFFERED rows so their future ordering is
    # also current-distance based without displacing live offered drivers.
    waiting = [
        offer
        for offer in existing_offers.values()
        if offer.status == "WAITING"
    ]

    waiting.sort(
        key=lambda offer: (
            float(offer.distance_miles),
            int(offer.driver_id),
        )
    )

    for offset, offer in enumerate(
        waiting,
        start=len(offered) + 1,
    ):
        if int(offer.rank) != offset:
            offer.rank = offset
            changed.append(offer)

    offered_ids = {
        int(offer.driver_id)
        for offer in offered
    }

    invariant_missing = (
        inside_driver_ids
        - offered_ids
        - {
            int(offer.driver_id)
            for offer in existing_offers.values()
            if offer.status == "DECLINED"
        }
    )

    print(
        "[LIVE QUEUE SNAPSHOT] "
        f"trip={trip.id} "
        f"radius={search_radius:.3f}mi "
        f"max_radius={max_radius:.3f}mi "
        f"live={len(live_driver_ids)} "
        f"inside={len(inside_driver_ids)} "
        f"offered={len(offered)} "
        f"waiting={len(waiting)} "
        f"missing={sorted(invariant_missing)}",
        flush=True,
    )

    _refresh_trip_dispatch_summary(
        trip
    )

    db.session.commit()

    unique_changed = []
    seen = set()

    for offer in changed:
        key = (
            int(offer.id)
            if offer.id is not None
            else id(offer)
        )

        if key in seen:
            continue

        seen.add(key)
        unique_changed.append(offer)

    return unique_changed
