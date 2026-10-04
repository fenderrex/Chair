from app.extensions import db
from app.trips.models import Trip
from app.trips.state import REQUESTED, OFFERED
from .proximity import activate_due_offers


def process_proximity_service():
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

    events = []

    for trip_id in trip_ids:
        changed_rows = (
            activate_due_offers(
                trip_id
            )
            or []
        )

        newly_offered_driver_ids = sorted({
            int(row.driver_id)
            for row in changed_rows
            if getattr(
                row,
                "_became_offered_this_tick",
                False,
            )
        })

        if changed_rows:
            events.append({
                "trip_id": int(trip_id),
                "new_driver_ids":
                    newly_offered_driver_ids,
            })

    return events
