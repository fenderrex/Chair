from app.extensions import db, socketio
from app.dispatch.timing import utcnow
from app.dispatch.queue import _refresh_trip_dispatch_summary
from .models import Trip, RideOffer, FareEscalation
from .state import REQUESTED, OFFERED, DRIVER_ASSIGNED, DRIVER_EN_ROUTE, DRIVER_ARRIVED, PICKUP_PENDING, IN_PROGRESS
from .timing import iso_utc


def _close_other_offers(
    trip_id,
    accepted_offer_id=None,
):
    now = utcnow()

    offers = (
        RideOffer.query
        .filter_by(
            trip_id=trip_id
        )
        .all()
    )

    for offer in offers:
        if (
            accepted_offer_id
            and offer.id ==
            accepted_offer_id
        ):
            continue

        if offer.status in {
            "OFFERED",
            "WAITING",
        }:
            offer.status = "CLOSED"
            offer.closed_at = now

def accept_trip_offer(
    trip_id,
    driver_id,
):
    trip = (
        Trip.query
        .filter_by(
            id=trip_id
        )
        .with_for_update()
        .first()
    )

    if trip is None:
        raise ValueError(
            "Trip not found"
        )

    if trip.status != OFFERED:
        raise ValueError(
            "This ride is no longer available"
        )

    offer = (
        RideOffer.query
        .filter_by(
            trip_id=trip.id,
            driver_id=driver_id,
        )
        .with_for_update()
        .first()
    )

    if (
        offer is None
        or offer.status != "OFFERED"
    ):
        raise ValueError(
            "This ride is not currently available to this driver"
        )

    from app.drivers.models import Driver
    driver = Driver.query.filter_by(id=driver_id).populate_existing().with_for_update().first()

    if (
        driver is None
        or not driver.is_online
        or not driver.is_available
    ):
        raise ValueError(
            "Driver is no longer available"
        )

    vehicle = (
        driver.vehicles[0]
        if driver.vehicles
        else None
    )

    now = utcnow()
    offer.status = "ACCEPTED"
    offer.accepted_at = now

    if int(trip.fare_round or 0) > 0:
        driver.fare_increase_accept_count = int(
            driver.fare_increase_accept_count
            or 0
        ) + 1

        driver.last_fare_increase_accept_at = (
            now
        )

        print(
            "[DRIVER FARE-INCREASE ACCEPTANCE NOTED] "
            f"driver={driver.id} "
            f"trip={trip.id} "
            f"fare_round={trip.fare_round} "
            f"fare=${trip.estimated_fare:.2f} "
            f"count={driver.fare_increase_accept_count}",
            flush=True,
        )

    pending_escalations = (
        FareEscalation.query
        .filter_by(
            trip_id=trip.id,
            status="PENDING",
        )
        .all()
    )

    for escalation in pending_escalations:
        escalation.status = "SUPERSEDED"
        escalation.responded_at = now

    _close_other_offers(
        trip.id,
        accepted_offer_id=
            offer.id,
    )

    trip.driver_id = driver.id

    trip.vehicle_id = (
        vehicle.id
        if vehicle
        else None
    )

    trip.status = DRIVER_ASSIGNED

    trip.accepted_at = now

    trip.next_dispatch_at = None
    trip.fare_wait_until = None
    trip.fare_review_pending = False

    # Matching/collision lane permanently closes once a driver accepts.
    trip.collision_dirty = False
    trip.collision_reason = None
    trip.collision_requested_at = None

    trip.offered_driver_id = driver.id

    trip.offer_rank = offer.rank

    driver.is_available = False

    db.session.commit()

    socketio.emit(
        "ride_accepted",
        {
            "trip_id":
                trip.id,

            "driver_id":
                driver.id,

            "driver_name":
                driver.display_name,

            "status":
                trip.status,

            "accepted_rank":
                offer.rank,

            "pickup_eta_seconds":
                offer.pickup_eta_seconds,
        },
    )

    return (
        trip,
        driver,
    )

def decline_trip_offer(
    trip_id,
    driver_id,
):
    trip = (
        Trip.query
        .filter_by(
            id=trip_id
        )
        .with_for_update()
        .first()
    )

    if trip is None:
        raise ValueError(
            "Trip not found"
        )

    offer = (
        RideOffer.query
        .filter_by(
            trip_id=trip.id,
            driver_id=driver_id,
        )
        .with_for_update()
        .first()
    )

    if (
        offer is None
        or offer.status != "OFFERED"
    ):
        raise ValueError(
            "There is no active offer for this driver"
        )

    offer.status = "DECLINED"
    offer.declined_at = utcnow()

    db.session.commit()

    from app.dispatch.collision import (
        mark_trip_collision_dirty,
    )

    trip = db.session.get(
        Trip,
        trip.id,
    )

    mark_trip_collision_dirty(
        trip,
        f"DRIVER_DECLINED:{driver_id}",
        commit=True,
    )

    socketio.emit(
        "ride_declined",
        {
            "trip_id":
                trip.id,
            "driver_id":
                driver_id,
        },
        room=
            f"driver:{driver_id}",
    )

    return trip

def driver_mark_arrived(
    trip_id,
    driver_id,
):
    trip = (
        Trip.query
        .filter_by(id=trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        raise ValueError("Trip not found")

    if trip.driver_id != int(driver_id):
        raise ValueError("Trip is not assigned to this driver")

    # Network retries are safe: once arrival is recorded, return the same
    # trip without resetting the passenger's waiting-clock timestamp.
    if trip.status == DRIVER_ARRIVED:
        return trip, False

    if trip.status != DRIVER_EN_ROUTE:
        raise ValueError(
            "Driver can only mark arrival while en route to pickup"
        )

    now = utcnow()
    trip.status = DRIVER_ARRIVED
    trip.driver_arrived_at = now
    trip.driver_eta_seconds = 0
    trip.progress_percent = 100.0

    db.session.commit()

    socketio.emit(
        "driver_arrived",
        {
            "trip_id": trip.id,
            "driver_id": trip.driver_id,
            "status": trip.status,
            "driver_arrived_at": iso_utc(trip.driver_arrived_at),
        },
        room=f"trip:{trip.id}",
    )

    return trip, True


def driver_claim_pickup(
    trip_id,
    driver_id,
):
    trip = (
        Trip.query
        .filter_by(id=trip_id)
        .with_for_update()
        .first()
    )

    if trip is None:
        raise ValueError("Trip not found")

    if trip.driver_id != int(driver_id):
        raise ValueError("Trip is not assigned to this driver")

    if trip.status != "DRIVER_ARRIVED":
        raise ValueError(
            "Passenger pickup can only be claimed after the driver has arrived"
        )

    now = utcnow()

    trip.status = PICKUP_PENDING
    trip.pickup_claimed_at = now

    # Lock cancellation immediately once the driver says the passenger
    # is physically in the vehicle. Passenger confirmation finalizes
    # IN_PROGRESS, but the ride can no longer be canceled in between.
    if trip.cancel_locked_at is None:
        trip.cancel_locked_at = now

    db.session.commit()

    socketio.emit(
        "pickup_claimed",
        {
            "trip_id": trip.id,
            "driver_id": trip.driver_id,
            "status": trip.status,
            "pickup_claimed_at": trip.pickup_claimed_at.isoformat(),
        },
        room=f"trip:{trip.id}",
    )

    return trip

def passenger_request_pickup_help(
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

    if trip.status != PICKUP_PENDING:
        raise ValueError(
            "Pickup help can only be requested while pickup confirmation is pending"
        )

    if trip.pickup_help_requested_at is None:
        trip.pickup_help_requested_at = utcnow()

    db.session.commit()

    socketio.emit(
        "pickup_help_requested",
        {
            "trip_id": trip.id,
            "driver_id": trip.driver_id,
            "passenger_id": trip.passenger_id,
            "passenger_name": trip.passenger_name,
            "status": trip.status,
            "pickup_help_requested_at": (
                trip.pickup_help_requested_at.isoformat()
            ),
        },
        room=f"trip:{trip.id}",
    )

    return trip

def passenger_confirm_pickup(
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

    if trip.status != PICKUP_PENDING:
        raise ValueError("Pickup is not waiting for passenger confirmation")

    now = utcnow()

    # Lock and retire the pickup-motion job in the SAME transaction as the
    # passenger confirmation. This prevents a due TO_PICKUP step from writing
    # DRIVER_EN_ROUTE after the passenger has already confirmed pickup.
    from app.broker.models import SimulationJob

    pickup_job = (
        SimulationJob.query
        .filter_by(
            trip_id=trip.id,
        )
        .with_for_update()
        .first()
    )

    if (
        pickup_job is not None
        and pickup_job.phase
        == "TO_PICKUP"
    ):
        pickup_job.status = "COMPLETED"
        pickup_job.next_due_at = None
        pickup_job.completed_at = now

        print(
            "[PICKUP JOB RETIRED] "
            f"trip={trip.id} "
            f"job={pickup_job.id} "
            f"index={pickup_job.current_index} "
            f"progress={pickup_job.progress_percent:.1f}%",
            flush=True,
        )

    trip.status = IN_PROGRESS
    trip.pickup_confirmed_at = now
    trip.started_at = trip.started_at or now

    if trip.cancel_locked_at is None:
        trip.cancel_locked_at = now

    db.session.commit()

    # Confirmation changes only real trip state and retires any old pickup
    # simulation. A fresh TO_DESTINATION job is prepared only when the driver
    # later presses Continue Ride.

    socketio.emit(
        "pickup_confirmed",
        {
            "trip_id": trip.id,
            "driver_id": trip.driver_id,
            "passenger_id": trip.passenger_id,
            "status": trip.status,
            "pickup_confirmed_at": trip.pickup_confirmed_at.isoformat(),
        },
        room=f"trip:{trip.id}",
    )

    return trip

def cancel_trip(
    trip_id,
    passenger_id=None,
    passenger_name=None,
):
    from .state import CANCELED
    from app.drivers.models import Driver

    trip = Trip.query.get_or_404(
        trip_id
    )

    if trip.status in {
        "COMPLETED",
        "CANCELED",
        "PICKUP_PENDING",
        "IN_PROGRESS",
    } or trip.cancel_locked_at is not None:
        raise ValueError(
            "Trip can no longer be canceled after passenger pickup begins"
        )

    if (
        passenger_id is not None
        and trip.passenger_id is not None
    ):
        if int(passenger_id) != int(
            trip.passenger_id
        ):
            raise ValueError(
                "Passenger does not own this trip"
            )

    elif (
        passenger_name
        and trip.passenger_name !=
        passenger_name
    ):
        raise ValueError(
            "Passenger does not own this trip"
        )

    previous_driver_id = (
        trip.driver_id
        or trip.offered_driver_id
    )

    trip.status = CANCELED
    trip.canceled_at = utcnow()
    trip.next_dispatch_at = None
    trip.fare_wait_until = None
    trip.fare_review_pending = False
    trip.collision_dirty = False
    trip.collision_reason = None
    trip.collision_requested_at = None

    _close_other_offers(
        trip.id
    )

    if previous_driver_id:
        driver = db.session.get(
            Driver,
            previous_driver_id,
        )

        if driver is not None:
            driver.is_available = True

    trip.driver_id = None
    trip.offered_driver_id = None
    trip.offered_at = None

    db.session.commit()

    socketio.emit(
        "ride_canceled",
        {
            "trip_id":
                trip.id,

            "status":
                trip.status,

            "passenger_name":
                trip.passenger_name,
        },
    )

    return trip
