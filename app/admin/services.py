from app.extensions import db
from app.users.models import User
from app.drivers.models import Driver, Vehicle
from app.trips.models import Trip, RideOffer, FareEscalation
from app.messages.models import Message
from app.location.models import LocationUpdate
from app.payments.models import Payment
from app.id_processing.models import IdentityDocument
from app.broker.models import SimulationJob
from app.surveys.models import RideSurvey


def dashboard_counts():

    return {
        "users": User.query.count(),
        "drivers": Driver.query.count(),
        "trips": Trip.query.count(),
        "messages": Message.query.count(),
    }


def recent_trips(limit=50):
    return Trip.query.order_by(Trip.created_at.desc()).limit(limit).all()


def all_drivers():
    return Driver.query.order_by(Driver.id.asc()).all()


def all_passengers():
    return (
        User.query
        .filter(User.role == "PASSENGER")
        .order_by(User.display_name.asc(), User.id.asc())
        .all()
    )


def active_trip_requests():
    from app.trips.services import active_requests
    return active_requests()


def delete_trip(trip_id):
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        raise ValueError("Trip not found")

    # Lock and remove the broker job first so the subprocess cannot advance it.
    job = (
        SimulationJob.query
        .filter_by(trip_id=trip.id)
        .with_for_update()
        .first()
    )
    if job is not None:
        db.session.delete(job)
        db.session.flush()

    driver_id = trip.driver_id or trip.offered_driver_id
    if driver_id is not None:
        driver = db.session.get(Driver, driver_id)
        if driver is not None:
            driver.is_available = True

    from app.trips.models import TripStageEvent, TripNotice
    TripNotice.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    RideSurvey.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    TripStageEvent.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    FareEscalation.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    RideOffer.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    Message.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    LocationUpdate.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
    Payment.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)

    deleted_id = trip.id
    db.session.delete(trip)
    db.session.commit()
    from .live import publish_admin_trip
    publish_admin_trip(deleted_id)


def delete_driver(driver_id):
    driver = db.session.get(Driver, driver_id)
    if driver is None:
        raise ValueError("Driver not found")

    # Stop all simulation jobs owned by the driver before changing trip rows.
    jobs = (
        SimulationJob.query
        .filter_by(driver_id=driver.id)
        .with_for_update()
        .all()
    )
    for job in jobs:
        db.session.delete(job)
    db.session.flush()

    trips = Trip.query.filter(
        (Trip.driver_id == driver.id) |
        (Trip.offered_driver_id == driver.id)
    ).all()

    for trip in trips:
        if trip.status in {
            "REQUESTED",
            "OFFERED",
            "DRIVER_ASSIGNED",
            "DRIVER_EN_ROUTE",
            "DRIVER_ARRIVED",
            "PICKUP_PENDING",
            "IN_PROGRESS",
        }:
            trip.status = "CANCELED"
            from datetime import datetime, timezone
            trip.canceled_at = datetime.now(timezone.utc)
        trip.driver_id = None
        trip.offered_driver_id = None
        trip.vehicle_id = None

    RideOffer.query.filter_by(driver_id=driver.id).delete(synchronize_session=False)
    IdentityDocument.query.filter_by(driver_id=driver.id).delete(synchronize_session=False)
    Vehicle.query.filter_by(driver_id=driver.id).delete(synchronize_session=False)
    db.session.delete(driver)
    db.session.commit()
    from app.trips.stream import publish_trip_snapshot
    from .platform_map import publish_platform_map
    publish_platform_map()
    for trip in trips:
        publish_trip_snapshot(trip.id, reason="DRIVER_DELETED")


def delete_passenger(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError("Passenger not found")
    if user.role != "PASSENGER":
        raise ValueError("Selected user is not a passenger")

    # Keep historical trips but detach the deleted account from them.
    trips = Trip.query.filter_by(passenger_id=user.id).all()
    for trip in trips:
        trip.passenger_id = None
        if trip.status in {
            "REQUESTED",
            "OFFERED",
            "DRIVER_ASSIGNED",
            "DRIVER_EN_ROUTE",
            "DRIVER_ARRIVED",
            "PICKUP_PENDING",
            "IN_PROGRESS",
        }:
            job = (
                SimulationJob.query
                .filter_by(trip_id=trip.id)
                .with_for_update()
                .first()
            )
            if job is not None:
                db.session.delete(job)

            active_driver_id = trip.driver_id or trip.offered_driver_id
            if active_driver_id is not None:
                driver = db.session.get(Driver, active_driver_id)
                if driver is not None:
                    driver.is_available = True

            trip.status = "CANCELED"
            from datetime import datetime, timezone
            trip.canceled_at = datetime.now(timezone.utc)
            trip.offered_driver_id = None

    db.session.delete(user)
    db.session.commit()
    from app.trips.stream import publish_trip_snapshot
    from .platform_map import publish_platform_map
    publish_platform_map()
    for trip in trips:
        publish_trip_snapshot(trip.id, reason="PASSENGER_DELETED")
