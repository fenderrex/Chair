from datetime import timedelta

from app.extensions import db
from app.trips.models import Trip, RideOffer, FareEscalation
from app.trips.state import REQUESTED, OFFERED
from app.trips.lifecycle import cancel_trip
from .timing import utcnow, comparable_now
from .radius import current_dispatch_expansion


def _maybe_start_last_driver_wait(trip):
    if trip.fare_review_pending:
        return False

    if trip.fare_wait_until is not None:
        return False

    offers = (
        RideOffer.query
        .filter_by(trip_id=trip.id)
        .all()
    )

    from app.admin.settings import get_dispatch_settings

    settings = get_dispatch_settings()
    clock = current_dispatch_expansion(
        trip,
        settings,
    )

    # The fare-review grace period begins at the configured geographic cap,
    # not merely when the currently-known farthest driver has been reached.
    if not clock["radius_capped"]:
        return False

    now = utcnow()

    trip.fare_wait_until = (
        now
        + timedelta(
            seconds=
                settings[
                    "last_driver_wait_seconds"
                ]
        )
    )

    print(
        "[PASSENGER SEARCH MAX RADIUS REACHED] "
        f"trip={trip.id} "
        f"radius={clock['search_radius_miles']:.3f}mi "
        f"increase_by={clock['radius_step_miles']:.3f}mi "
        f"max_radius={clock['max_radius_miles']:.3f}mi "
        f"grace={settings['last_driver_wait_seconds']}s",
        flush=True,
    )

    return True

def _maybe_open_fare_review(trip):
    if trip.fare_review_pending:
        return False

    if trip.fare_wait_until is None:
        return False

    if comparable_now(trip.fare_wait_until) < trip.fare_wait_until:
        return False

    offers = (
        RideOffer.query
        .filter_by(trip_id=trip.id)
        .all()
    )

    # At this point the search has reached the admin-configured maximum radius
    # and the grace timer has ended. OFFERED drivers intentionally remain
    # eligible while the passenger decides whether to raise the fare.

    if trip.no_driver_admin_notified_at is None:
        trip.no_driver_admin_notified_at = utcnow()

        print(
            "[ADMIN NO DRIVER ALERT] "
            f"trip={trip.id} "
            f"offered={sum(1 for offer in offers if offer.status == 'OFFERED')} "
            f"declined={sum(1 for offer in offers if offer.status == 'DECLINED')}",
            flush=True,
        )

    from app.admin.settings import get_dispatch_settings

    settings = get_dispatch_settings()

    original_fare = float(
        trip.original_estimated_fare
        if trip.original_estimated_fare is not None
        else trip.estimated_fare
    )

    next_round = int(
        trip.fare_round or 0
    ) + 1

    multiplier = float(
        settings["fare_multiplier"]
    )

    proposed_fare = round(
        original_fare
        * (
            multiplier
            ** next_round
        ),
        2,
    )

    existing = FareEscalation.query.filter_by(
        trip_id=trip.id,
        round_number=next_round,
    ).first()

    if existing is None:
        existing = FareEscalation(
            trip_id=trip.id,
            round_number=next_round,
            original_fare=original_fare,
            multiplier=multiplier,
            offered_fare=proposed_fare,
            status="PENDING",
            prompted_at=utcnow(),
        )
        db.session.add(existing)
    else:
        existing.original_fare = original_fare
        existing.multiplier = multiplier
        existing.offered_fare = proposed_fare
        existing.status = "PENDING"
        existing.prompted_at = utcnow()
        existing.responded_at = None

    trip.fare_multiplier = multiplier
    trip.fare_review_pending = True

    print(
        "[FARE ESCALATION REVIEW] "
        f"trip={trip.id} "
        f"round={next_round} "
        f"original=${original_fare:.2f} "
        f"multiplier={multiplier:.4f} "
        f"proposed=${proposed_fare:.2f}",
        flush=True,
    )

    return True

def process_fare_escalation_watch(trip):
    changed = False

    if _maybe_start_last_driver_wait(trip):
        changed = True

    if _maybe_open_fare_review(trip):
        changed = True

    return changed

def accept_fare_escalation(
    trip_id,
    passenger_id=None,
):
    trip = (
        Trip.query
        .filter_by(id=trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        raise ValueError("Trip not found")

    if (
        passenger_id is not None
        and trip.passenger_id is not None
        and int(passenger_id) != int(trip.passenger_id)
    ):
        raise ValueError("Passenger does not own this trip")

    if not trip.fare_review_pending:
        raise ValueError(
            "There is no fare increase waiting for passenger approval"
        )

    next_round = int(
        trip.fare_round or 0
    ) + 1

    escalation = (
        FareEscalation.query
        .filter_by(
            trip_id=trip.id,
            round_number=next_round,
            status="PENDING",
        )
        .with_for_update()
        .first()
    )

    if escalation is None:
        raise ValueError(
            "Fare escalation record was not found"
        )

    now = utcnow()

    escalation.status = "ACCEPTED"
    escalation.responded_at = now

    from app.admin.settings import get_dispatch_settings

    settings = get_dispatch_settings()
    timer_seconds = max(
        0.001,
        float(settings["expansion_seconds"]),
    )
    initial_radius = max(
        0.0,
        float(settings.get("initial_radius_miles", 3.0)),
    )
    radius_step = max(
        0.001,
        float(settings["radius_miles"]),
    )
    max_radius = max(
        initial_radius,
        float(settings["max_radius_miles"]),
    )

    trip.fare_round = next_round
    trip.fare_multiplier = escalation.multiplier
    trip.estimated_fare = escalation.offered_fare
    trip.fare_review_pending = False
    trip.fare_wait_until = None
    trip.no_driver_admin_notified_at = None
    trip.status = REQUESTED

    # A passenger-approved fare increase starts a new search round. Keep the
    # existing driver rows so the driver UI never goes blank, but reset the
    # search clock and move known drivers back to WAITING until the broker's
    # expanding radius reaches them again at the new fare.
    trip.dispatch_started_at = now
    trip.next_dispatch_at = (
        now + timedelta(seconds=timer_seconds)
    )
    trip.dispatch_wave = 0
    trip.offered_driver_id = None
    trip.offered_at = None
    trip.offer_rank = None

    offers = (
        RideOffer.query
        .filter_by(trip_id=trip.id)
        .with_for_update()
        .all()
    )

    reset_driver_ids = []

    for offer in offers:
        distance = max(
            0.0,
            float(offer.distance_miles or 0.0),
        )

        # Drivers outside the admin cap are not part of this fare round. A
        # later location update can reopen them if they move inside the cap.
        if distance > max_radius:
            offer.status = "CLOSED"
            offer.eligible_at = now
            offer.offered_at = now
            offer.expires_at = None
            offer.closed_at = now
            continue

        if distance <= initial_radius:
            interval_number = 0
            offer.status = "OFFERED"
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
            offer.status = "WAITING"

        offer.eligible_at = (
            now
            + timedelta(
                seconds=interval_number * timer_seconds
            )
        )
        offer.offered_at = (
            now if offer.status == "OFFERED" else None
        )
        offer.expires_at = None
        offer.declined_at = None
        offer.accepted_at = None
        offer.closed_at = None
        offer.response_seconds = None
        offer.distance_fraction = distance / radius_step
        reset_driver_ids.append(int(offer.driver_id))

    db.session.commit()

    print(
        "[FARE ROUND SEARCH RESET] "
        f"trip={trip.id} "
        f"round={next_round} "
        f"fare=${trip.estimated_fare:.2f} "
        f"radius={initial_radius:.3f}mi "
        f"step={radius_step:.3f}mi "
        f"max_radius={max_radius:.3f}mi "
        f"interval={timer_seconds:.2f}s "
        f"waiting_drivers={len(reset_driver_ids)}",
        flush=True,
    )

    from app.dispatch.collision import (
        mark_trip_collision_dirty,
    )

    trip = db.session.get(
        Trip,
        trip.id,
    )

    mark_trip_collision_dirty(
        trip,
        "FARE_ROUND_RESTART",
        commit=True,
    )

    # Apply the reset radius immediately. Do not leave the UI waiting for the
    # next broker tick to discover which drivers are already inside the new
    # starting radius. This also publishes the reset search circle at once.
    from app.dispatch.proximity import activate_due_offers
    from app.dispatch.events import publish_proximity_event

    activate_due_offers(
        trip.id
    )

    offered_driver_ids = [
        int(row[0])
        for row in (
            db.session.query(RideOffer.driver_id)
            .filter(
                RideOffer.trip_id == trip.id,
                RideOffer.status == "OFFERED",
            )
            .all()
        )
    ]

    publish_proximity_event(
        trip.id,
        reason="FARE_ROUND_RESTARTED",
        new_driver_ids=offered_driver_ids,
    )

    print(
        "[FARE ESCALATION ACCEPTED] "
        f"trip={trip.id} "
        f"round={trip.fare_round} "
        f"fare=${trip.estimated_fare:.2f}",
        flush=True,
    )

    return trip

def decline_fare_escalation(
    trip_id,
    passenger_id=None,
):
    trip = (
        Trip.query
        .filter_by(id=trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        raise ValueError("Trip not found")

    if (
        passenger_id is not None
        and trip.passenger_id is not None
        and int(passenger_id) != int(trip.passenger_id)
    ):
        raise ValueError("Passenger does not own this trip")

    if not trip.fare_review_pending:
        raise ValueError(
            "There is no fare increase waiting for passenger approval"
        )

    next_round = int(
        trip.fare_round or 0
    ) + 1

    escalation = (
        FareEscalation.query
        .filter_by(
            trip_id=trip.id,
            round_number=next_round,
            status="PENDING",
        )
        .with_for_update()
        .first()
    )

    if escalation is not None:
        escalation.status = "DECLINED"
        escalation.responded_at = utcnow()

    trip.fare_review_pending = False
    trip.fare_wait_until = None

    db.session.commit()

    return cancel_trip(
        trip.id,
        passenger_id=passenger_id,
    )

def process_dispatch_queue():
    trip_ids = [
        row[0]
        for row in (
            db.session.query(Trip.id)
            .filter(
                Trip.status.in_(
                    [
                        REQUESTED,
                        OFFERED,
                    ]
                )
            )
            .order_by(Trip.id.asc())
            .all()
        )
    ]

    changed_trip_ids = []

    for trip_id in trip_ids:
        trip = db.session.get(
            Trip,
            trip_id,
        )

        fare_changed = False

        if trip is not None:
            fare_changed = (
                process_fare_escalation_watch(
                    trip
                )
            )

        if fare_changed:
            db.session.commit()
            changed_trip_ids.append(
                int(trip_id)
            )

    return changed_trip_ids
