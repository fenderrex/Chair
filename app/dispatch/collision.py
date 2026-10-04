from sqlalchemy import or_

from app.extensions import db
from app.trips.models import Trip, RideOffer
from app.trips.state import REQUESTED, OFFERED
from .timing import utcnow
from .proximity import activate_due_offers
from .fare_rounds import (
    process_fare_escalation_watch,
)
from .radius import current_dispatch_expansion


SEARCH_STATES = {
    REQUESTED,
    OFFERED,
}


def mark_trip_collision_dirty(
    trip,
    reason,
    *,
    commit=True,
):
    if trip is None:
        return False

    if trip.status not in SEARCH_STATES:
        return False

    trip.collision_dirty = True
    trip.collision_reason = str(
        reason
    )[:80]
    trip.collision_requested_at = (
        utcnow()
    )
    trip.collision_revision = int(
        trip.collision_revision or 0
    ) + 1

    if commit:
        db.session.commit()

    return True


def mark_active_searches_collision_dirty(
    reason,
):
    trips = (
        Trip.query
        .filter(
            Trip.status.in_(
                [
                    REQUESTED,
                    OFFERED,
                ]
            )
        )
        .all()
    )

    now = utcnow()

    for trip in trips:
        trip.collision_dirty = True
        trip.collision_reason = str(
            reason
        )[:80]
        trip.collision_requested_at = now
        trip.collision_revision = int(
            trip.collision_revision or 0
        ) + 1

    if trips:
        db.session.commit()

    return [
        int(trip.id)
        for trip in trips
    ]


def due_collision_trip_ids():
    """
    Read-only collision lane query.

    Collision work runs when:
      - a rider request/driver position write marked the trip dirty;
      - the next radius expansion time arrived; or
      - fare-wait timing became due.
    """
    now = utcnow()

    return [
        int(row[0])
        for row in (
            db.session.query(
                Trip.id
            )
            .filter(
                Trip.status.in_(
                    [
                        REQUESTED,
                        OFFERED,
                    ]
                ),
                Trip.fare_review_pending
                .is_(False),
                or_(
                    Trip.collision_dirty
                    .is_(True),
                    (
                        Trip.next_dispatch_at
                        .is_not(None)
                    )
                    & (
                        Trip.next_dispatch_at
                        <= now
                    ),
                    (
                        Trip.fare_wait_until
                        .is_not(None)
                    )
                    & (
                        Trip.fare_wait_until
                        <= now
                    ),
                ),
            )
            .order_by(
                Trip.id.asc()
            )
            .all()
        )
    ]


def _consume_collision_trigger(
    trip_id,
):
    trip = (
        Trip.query
        .filter_by(
            id=int(trip_id)
        )
        .with_for_update()
        .first()
    )

    if (
        trip is None
        or trip.status
        not in SEARCH_STATES
    ):
        return None

    now = utcnow()

    if trip.collision_dirty:
        reason = (
            trip.collision_reason
            or "COLLISION_DIRTY"
        )
    elif (
        trip.fare_wait_until
        is not None
        and trip.fare_wait_until
        <= (
            now.replace(tzinfo=None)
            if (
                trip.fare_wait_until.tzinfo
                is None
                and now.tzinfo
                is not None
            )
            else now
        )
    ):
        reason = "FARE_WAIT_DUE"
    else:
        reason = "SEARCH_RADIUS_DUE"

    revision = int(
        trip.collision_revision or 0
    )

    trip.collision_dirty = False
    trip.collision_reason = None
    trip.collision_requested_at = None

    db.session.commit()

    return {
        "reason": reason,
        "collision_revision":
            revision,
    }


def run_collision_check(
    trip_id,
):
    trigger = _consume_collision_trigger(
        trip_id
    )

    if trigger is None:
        return None

    changed_rows = (
        activate_due_offers(
            int(trip_id)
        )
        or []
    )

    matched_driver_ids = []
    unmatched_driver_ids = []
    affected_driver_ids = set()

    for row in changed_rows:
        driver_id = int(
            row.driver_id
        )
        affected_driver_ids.add(
            driver_id
        )

        if getattr(
            row,
            "_became_offered_this_tick",
            False,
        ):
            matched_driver_ids.append(
                driver_id
            )

        if getattr(
            row,
            "_left_offer_this_tick",
            False,
        ) or getattr(
            row,
            "_removed_from_search_tick",
            False,
        ):
            unmatched_driver_ids.append(
                driver_id
            )

    trip = db.session.get(
        Trip,
        int(trip_id),
    )

    fare_changed = False

    if trip is not None:
        fare_changed = bool(
            process_fare_escalation_watch(
                trip
            )
        )

        if fare_changed:
            db.session.commit()

    trip = db.session.get(
        Trip,
        int(trip_id),
    )

    if trip is None:
        return None

    from app.admin.settings import (
        get_dispatch_settings,
    )

    clock = current_dispatch_expansion(
        trip,
        get_dispatch_settings(),
    )

    open_offer_count = (
        RideOffer.query
        .filter_by(
            trip_id=trip.id,
            status="OFFERED",
        )
        .count()
    )

    return {
        "trip_id": trip.id,
        "trigger_reason":
            trigger["reason"],
        "collision_revision":
            trigger[
                "collision_revision"
            ],
        "matched_driver_ids":
            sorted(
                set(
                    matched_driver_ids
                )
            ),
        "unmatched_driver_ids":
            sorted(
                set(
                    unmatched_driver_ids
                )
            ),
        "affected_driver_ids":
            sorted(
                affected_driver_ids
            ),
        "fare_changed":
            fare_changed,
        "search_radius_miles":
            float(
                clock[
                    "search_radius_miles"
                ]
            ),
        "reviewing_count":
            int(
                open_offer_count
            ),
        "status":
            trip.status,
    }
