import json

from app.extensions import db, socketio
from app.dispatch.timing import utcnow
from app.dispatch.fare import calculate_fare_estimate
from app.dispatch.plan import build_dispatch_plan
from .models import Trip, RideOffer
from .state import REQUESTED, ACTIVE_REQUEST_STATES


def get_active_trip_for_passenger(
    passenger_id=None,
    passenger_name=None,
):
    active_states = [
        "REQUESTED",
        "OFFERED",
        "DRIVER_ASSIGNED",
        "DRIVER_EN_ROUTE",
        "DRIVER_ARRIVED",
        "PICKUP_PENDING",
        "IN_PROGRESS",
    ]

    query = Trip.query.filter(
        Trip.status.in_(active_states)
    )

    if passenger_id is not None:
        query = query.filter(
            Trip.passenger_id == int(passenger_id)
        )
    elif passenger_name:
        query = query.filter(
            Trip.passenger_name == str(passenger_name)
        )
    else:
        return None

    return (
        query
        .order_by(Trip.created_at.desc())
        .first()
    )

def create_trip_request(
    payload,
    route,
):
    passenger_id = payload.get("passenger_id")

    existing_trip = get_active_trip_for_passenger(
        passenger_id=passenger_id,
        passenger_name=payload.get("passenger_name"),
    )

    if existing_trip is not None:
        raise ValueError(
            f"Passenger already has active trip #{existing_trip.id}"
        )

    fare = calculate_fare_estimate(
        route
    )

    from app.admin.settings import get_dispatch_settings
    dispatch_settings = get_dispatch_settings()

    trip = Trip(
        passenger_id=
            payload.get(
                "passenger_id"
            ),

        passenger_name=
            payload.get(
                "passenger_name",
                "Demo Passenger",
            ),

        driver_id=None,
        vehicle_id=None,
        status=REQUESTED,

        pickup_latitude=
            float(
                payload["pickup_lat"]
            ),

        pickup_longitude=
            float(
                payload["pickup_lng"]
            ),

        passenger_current_latitude=
            float(
                payload["pickup_lat"]
            ),

        passenger_current_longitude=
            float(
                payload["pickup_lng"]
            ),

        destination_latitude=
            float(
                payload["destination_lat"]
            ),

        destination_longitude=
            float(
                payload["destination_lng"]
            ),

        estimated_distance_meters=
            route["distance_meters"],

        estimated_duration_seconds=
            route["duration_seconds"],

        estimated_fare=
            fare["estimated_total"],

        original_estimated_fare=
            fare["estimated_total"],

        fare_multiplier=
            dispatch_settings["fare_multiplier"],

        fare_round=0,
        fare_wait_until=None,
        fare_review_pending=False,

        route_provider=
            route["provider"],

        route_geometry_json=
            json.dumps(
                route["geometry"]
            ),

        dispatch_started_at=
            utcnow(),

        dispatch_wave=0,
    )

    db.session.add(
        trip
    )

    db.session.commit()

    build_dispatch_plan(
        trip.id
    )

    # Reconcile the initial radius immediately instead of waiting for the
    # first broker interval. This guarantees every currently eligible driver
    # inside the starting radius gets an OFFERED row before the first UI
    # snapshot, and it makes the admin/passenger search circle visible at the
    # configured starting radius right away.
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
        reason="INITIAL_SEARCH_STARTED",
        new_driver_ids=offered_driver_ids,
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
        "RIDER_REQUEST",
        commit=True,
    )

    socketio.emit(
        "trip_requested",
        {"trip_id": trip.id},
    )

    return (
        trip,
        fare,
        True,
    )

def active_requests():
    return (
        Trip.query
        .filter(
            Trip.status.in_(
                ACTIVE_REQUEST_STATES
            )
        )
        .order_by(
            Trip.requested_at.asc()
        )
        .all()
    )
