import logging

from app.extensions import db, socketio
from app.trips.models import Trip, RideOffer
from app.trips.stream import publish_trip_snapshot
from app.drivers.socket_events import emit_driver_queue
from .serialization import serialize_trip_request

log = logging.getLogger("rideshare.dispatch_events")


def publish_proximity_event(
    trip_id,
    *,
    reason="PROXIMITY_MATCH_CHANGED",
    new_driver_ids=None,
):
    """
    Push a persisted dispatch change to passenger and driver clients.

    This is shared by:
      - the background broker callback
      - demo map movement
      - any future production location-triggered fast path

    Database rows remain authoritative.
    """
    trip_id = int(trip_id)
    new_driver_ids = {
        int(driver_id)
        for driver_id in (
            new_driver_ids
            or []
        )
    }

    snapshot = publish_trip_snapshot(
        trip_id,
        reason=reason,
    )

    if snapshot is None:
        return None

    # Search/offer fan-out is only valid while this trip is actually in the
    # dispatch phase. Once assigned, movement snapshots must not rebuild every
    # historical offer driver's queue.
    dispatch_active = (
        snapshot.get("status")
        in {"REQUESTED", "OFFERED"}
    )

    if not dispatch_active:
        return snapshot

    all_driver_ids = {
        int(row[0])
        for row in (
            db.session.query(
                RideOffer.driver_id
            )
            .filter(
                RideOffer.trip_id
                == trip_id
            )
            .all()
        )
    }

    offered_driver_ids = {
        int(row[0])
        for row in (
            db.session.query(
                RideOffer.driver_id
            )
            .filter(
                RideOffer.trip_id
                == trip_id,
                RideOffer.status
                == "OFFERED",
            )
            .all()
        )
    }

    trip = db.session.get(
        Trip,
        trip_id,
    )

    for driver_id in sorted(
        all_driver_ids
    ):
        emit_driver_queue(
            driver_id
        )

        if (
            trip is not None
            and driver_id
            in offered_driver_ids
            and driver_id
            in new_driver_ids
        ):
            payload = (
                serialize_trip_request(
                    trip,
                    driver_id=driver_id,
                )
            )

            socketio.emit(
                "ride_offer",
                payload,
                room=f"driver:{driver_id}",
            )

            socketio.emit(
                "review_fare",
                {
                    "trip_id":
                        trip_id,
                    "driver_id":
                        driver_id,
                    "fare":
                        trip.estimated_fare,
                    "distance_miles":
                        payload.get(
                            "driver_distance_miles"
                        ),
                    "message":
                        "A passenger search reached you. Review the fare.",
                },
                room=f"driver:{driver_id}",
            )

    if new_driver_ids:
        reviewing = (
            snapshot.get(
                "dispatch",
                {},
            ).get(
                "reviewing_drivers",
                [],
            )
        )

        just_added = [
            item
            for item in reviewing
            if int(
                item.get(
                    "driver_id",
                    -1,
                )
            )
            in new_driver_ids
        ]

        socketio.emit(
            "drivers_reviewing_offer",
            {
                "trip_id":
                    trip_id,
                "fare":
                    snapshot.get(
                        "estimated_fare"
                    ),
                "drivers":
                    just_added,
                "reviewing_count":
                    len(reviewing),
            },
            room=f"trip:{trip_id}",
        )

    if snapshot.get(
        "no_driver_admin_notified_at"
    ):
        from app.admin.settings import (
            get_dispatch_settings,
        )

        settings = get_dispatch_settings()

        socketio.emit(
            "admin_dispatch_alert",
            {
                "trip_id":
                    trip_id,
                "passenger_id":
                    snapshot.get(
                        "passenger_id"
                    ),
                "passenger_name":
                    snapshot.get(
                        "passenger_name"
                    ),
                "radius_miles":
                    settings["radius_miles"],
                "driver_count":
                    len(all_driver_ids),
                "message":
                    "No driver accepted this ride.",
                "created_at":
                    snapshot[
                        "no_driver_admin_notified_at"
                    ],
            },
            room="admin:live",
        )

    return snapshot
