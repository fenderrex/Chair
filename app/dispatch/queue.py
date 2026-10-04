from app.extensions import db
from app.trips.models import RideOffer
from datetime import timedelta

from app.trips.state import REQUESTED, OFFERED


def _driver_offer_for_trip(
    trip_id,
    driver_id,
):
    if driver_id is None:
        return None

    return RideOffer.query.filter_by(
        trip_id=trip_id,
        driver_id=driver_id,
    ).first()

def _open_offers(trip_id):
    return (
        RideOffer.query
        .filter_by(
            trip_id=trip_id,
            status="OFFERED",
        )
        .order_by(
            RideOffer.rank.asc()
        )
        .all()
    )

def _waiting_offers(trip_id):
    return (
        RideOffer.query
        .filter_by(
            trip_id=trip_id,
            status="WAITING",
        )
        .order_by(
            RideOffer.eligible_at.asc(),
            RideOffer.rank.asc(),
        )
        .all()
    )

def _refresh_trip_dispatch_summary(trip):
    open_offers = _open_offers(trip.id)
    waiting = _waiting_offers(trip.id)

    trip.dispatch_wave = len(open_offers)

    if open_offers:
        best = open_offers[0]
        trip.status = OFFERED
        trip.offered_driver_id = best.driver_id
        trip.offered_at = best.offered_at
        trip.offer_rank = best.rank
    else:
        trip.offered_driver_id = None
        trip.offered_at = None
        trip.offer_rank = None

        trip.status = REQUESTED

    # Keep the broker clock moving at every configured radius interval, even
    # when there is no driver exactly at the next threshold. This makes the
    # search circle expand continuously until the admin maximum radius is hit.
    from app.admin.settings import get_dispatch_settings
    from .radius import current_dispatch_expansion

    settings = get_dispatch_settings()
    clock = current_dispatch_expansion(trip, settings)

    if trip.dispatch_started_at is not None and not clock["radius_capped"]:
        next_interval = int(clock["completed_intervals"]) + 1
        trip.next_dispatch_at = (
            trip.dispatch_started_at
            + timedelta(
                seconds=(
                    next_interval
                    * float(clock["total_seconds"])
                )
            )
        )
    else:
        trip.next_dispatch_at = None
