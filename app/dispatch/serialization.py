import json

from app.trips.timing import iso_utc
from app.trips.state import OFFERED
from .timing import utcnow, seconds_until
from .radius import current_dispatch_expansion
from .queue import _driver_offer_for_trip, _open_offers, _waiting_offers
from .fare import estimate_pickup_eta_seconds


def serialize_trip_request(
    trip,
    driver_id=None,
):
    my_offer = _driver_offer_for_trip(
        trip.id,
        driver_id,
    )

    open_offers = _open_offers(
        trip.id
    )

    waiting = _waiting_offers(
        trip.id
    )

    next_dispatch_at = (
        trip.next_dispatch_at.isoformat()
        if trip.next_dispatch_at
        else None
    )

    from app.admin.settings import get_dispatch_settings

    dispatch_clock = current_dispatch_expansion(
        trip,
        get_dispatch_settings(),
    )

    live_driver_distance_miles = (
        float(my_offer.distance_miles)
        if my_offer
        and my_offer.distance_miles is not None
        else None
    )

    if driver_id is not None:
        from app.drivers.models import Driver
        from app.drivers.services import haversine_miles

        driver = (
            Driver.query
            .filter_by(id=int(driver_id))
            .populate_existing()
            .first()
        )

        if (
            driver is not None
            and driver.current_latitude is not None
            and driver.current_longitude is not None
        ):
            live_driver_distance_miles = haversine_miles(
                float(trip.pickup_latitude),
                float(trip.pickup_longitude),
                float(driver.current_latitude),
                float(driver.current_longitude),
            )

    return {
        "trip_id": trip.id,
        "status": trip.status,
        "passenger_id": trip.passenger_id,
        "passenger_name": trip.passenger_name,

        "pickup": {
            "latitude": trip.pickup_latitude,
            "longitude": trip.pickup_longitude,
        },

        "destination": {
            "latitude": trip.destination_latitude,
            "longitude": trip.destination_longitude,
        },

        "estimated_fare":
            trip.estimated_fare,

        "original_estimated_fare": (
            trip.original_estimated_fare
            if trip.original_estimated_fare is not None
            else trip.estimated_fare
        ),

        "fare_round":
            trip.fare_round,

        "fare_multiplier":
            trip.fare_multiplier,

        "fare_increase_acceptance_note":
            bool(
                int(trip.fare_round or 0)
                > 0
            ),

        "previous_estimated_fare": (
            round(
                float(
                    trip.original_estimated_fare
                    if trip.original_estimated_fare is not None
                    else trip.estimated_fare
                )
                * (
                    float(trip.fare_multiplier or 1.0)
                    ** max(
                        0,
                        int(trip.fare_round or 0) - 1,
                    )
                ),
                2,
            )
            if int(trip.fare_round or 0) > 0
            else None
        ),

        "fare_increase_warning": (
            "This passenger increased the fare after the initial search. "
            "Accepting this higher-fare round will be recorded on your driver account."
            if int(trip.fare_round or 0) > 0
            else None
        ),

        "estimated_distance_meters":
            trip.estimated_distance_meters,

        "estimated_duration_seconds":
            trip.estimated_duration_seconds,

        "route_provider":
            trip.route_provider,

        "route_geometry":
            json.loads(
                trip.route_geometry_json
            ),

        "dispatch_wave":
            trip.dispatch_wave,

        "dispatch_elapsed_seconds":
            dispatch_clock["elapsed_seconds"],

        "dispatch_remaining_seconds":
            dispatch_clock["remaining_seconds"],

        "dispatch_expansion_fraction":
            dispatch_clock["expansion_fraction"],

        "search_radius_miles":
            dispatch_clock["search_radius_miles"],

        "initial_search_radius_miles":
            dispatch_clock["initial_radius_miles"],

        "search_radius_step_miles":
            dispatch_clock["radius_step_miles"],

        "max_search_radius_miles":
            dispatch_clock["max_radius_miles"],

        "search_radius_capped":
            dispatch_clock["radius_capped"],

        "search_radius_paused":
            dispatch_clock["radius_paused"],

        "next_dispatch_at":
            next_dispatch_at,

        "seconds_until_expand":
            seconds_until(
                trip.next_dispatch_at
            ),

        "offer_count":
            len(open_offers),

        "offered_driver_count":
            len(open_offers),

        "waiting_offer_count":
            len(waiting),

        "offered_driver_ids": [
            offer.driver_id
            for offer in open_offers
        ],

        "offer_expires_at": None,
        "server_time": iso_utc(utcnow()),
        "my_offer_status":
            my_offer.status
            if my_offer
            else None,

        "distance_fraction": my_offer.distance_fraction if my_offer else None,
        "my_offer_rank":
            my_offer.rank
            if my_offer
            else None,

        "driver_distance_miles": (
            round(
                live_driver_distance_miles,
                2,
            )
            if live_driver_distance_miles is not None
            else None
        ),

        "pickup_eta_seconds": (
            estimate_pickup_eta_seconds(
                live_driver_distance_miles
            )
            if live_driver_distance_miles is not None
            else None
        ),

        "eligible_at": (
            iso_utc(my_offer.eligible_at)
            if my_offer
            and my_offer.eligible_at
            else None
        ),

        "offer_available_at": (
            iso_utc(my_offer.eligible_at)
            if my_offer
            and my_offer.status == "WAITING"
            and my_offer.eligible_at
            else None
        ),

        "required_radius_miles": (
            round(
                min(
                    float(dispatch_clock["max_radius_miles"]),
                    float(dispatch_clock["initial_radius_miles"])
                    + max(
                        0,
                        __import__("math").ceil(
                            (
                                float(live_driver_distance_miles or 0.0)
                                - float(dispatch_clock["initial_radius_miles"])
                            )
                            / max(
                                0.001,
                                float(dispatch_clock["radius_step_miles"]),
                            )
                        ),
                    )
                    * max(
                        0.001,
                        float(dispatch_clock["radius_step_miles"]),
                    ),
                ),
                2,
            )
            if my_offer
            and my_offer.status == "WAITING"
            else None
        ),

        "seconds_until_eligible": (
            seconds_until(my_offer.eligible_at)
            if my_offer
            and my_offer.status == "WAITING"
            else 0
            if my_offer
            and my_offer.status == "OFFERED"
            else None
        ),

        "can_accept": bool(
            my_offer
            and my_offer.status == "OFFERED"
            and trip.status == OFFERED
        ),

        "can_decline": bool(
            my_offer
            and my_offer.status == "OFFERED"
            and trip.status == OFFERED
        ),

        "offered_driver_id":
            trip.offered_driver_id,

        "offer_rank":
            trip.offer_rank,

        "requested_at": (
            trip.requested_at.isoformat()
            if trip.requested_at
            else None
        ),
    }
