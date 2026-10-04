from app.trips.services import active_requests, serialize_trip_request
from app.trips.models import RideOffer
from app.extensions import db
from .models import Driver


def build_driver_request_queue(driver_id):
    """
    Driver queue mirrors authoritative active RideOffer rows, including
    WAITING rows so a known request remains visible while a new fare round
    expands back out to the driver.

    `is_available` is intentionally not used as a second queue gate here.
    The broker proximity service already determines whether the driver is
    actually free from active-trip assignments and reconciles offer status.
    """
    driver = (
        Driver.query
        .filter_by(id=int(driver_id))
        .populate_existing()
        .first()
    )

    if (
        driver is None
        or not driver.is_online
        or driver.verification_status
        != "APPROVED"
    ):
        return []

    visible_trip_ids = {
        int(row.trip_id)
        for row in (
            RideOffer.query
            .filter(
                RideOffer.driver_id == int(driver_id),
                RideOffer.status.in_([
                    "WAITING",
                    "OFFERED",
                    "DECLINED",
                ]),
            )
            .all()
        )
    }

    requests = [
        serialize_trip_request(
            trip,
            driver_id=int(driver_id),
        )
        for trip in active_requests()
        if int(trip.id)
        in visible_trip_ids
    ]

    state_priority = {
        "OFFERED": 0,
        "WAITING": 1,
        "DECLINED": 2,
    }

    requests.sort(
        key=lambda request: (
            state_priority.get(
                request.get("my_offer_status"),
                9,
            ),
            float(
                request.get(
                    "driver_distance_miles"
                )
                or 999999.0
            ),
            int(
                request.get(
                    "trip_id"
                )
                or 0
            ),
        )
    )

    return requests
