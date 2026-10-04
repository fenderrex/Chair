import math
import random
from datetime import datetime, timezone
from app.extensions import db, socketio
from app.drivers.models import Driver
from app.users.models import User
from app.trips.models import Trip
from app.trips.state import ACTIVE_TRIP_STATES
from app.location.models import LocationUpdate
from app.trips.timing import iso_utc


def platform_snapshot():
    from app.admin.settings import get_dispatch_settings
    from app.dispatch.radius import current_dispatch_expansion

    people = []
    dispatch_settings = get_dispatch_settings()
    drivers = Driver.query.order_by(Driver.id).all()
    driver_emails = {d.email for d in drivers}
    for driver in drivers:
        people.append({"key": f"driver:{driver.id}", "id": driver.id, "role": "DRIVER",
                       "name": driver.display_name, "status": "Offline" if not driver.is_online else
                       "Available" if driver.is_available else "Busy", "latitude": driver.current_latitude,
                       "longitude": driver.current_longitude, "location_kind": "Last reported driver position",
                       "recorded_at": iso_utc(driver.last_location_at)})
    for user in User.query.order_by(User.id).all():
        if user.role == "DRIVER" and user.email in driver_emails:
            continue
        person = {"key": f"user:{user.id}", "id": user.id, "role": user.role,
                  "name": user.display_name, "status": user.status, "latitude": None,
                  "longitude": None, "location_kind": "No location recorded", "recorded_at": None}
        if user.role == "PASSENGER":
            trip = Trip.query.filter_by(passenger_id=user.id).order_by(Trip.created_at.desc(), Trip.id.desc()).first()
            if trip:
                location = LocationUpdate.query.filter(LocationUpdate.trip_id == trip.id,
                    db.func.lower(LocationUpdate.actor_type) == "passenger").order_by(LocationUpdate.received_at.desc(), LocationUpdate.id.desc()).first()
                person.update(trip_id=trip.id, status=trip.status)
                if trip.status in {"REQUESTED", "OFFERED"}:
                    clock = current_dispatch_expansion(
                        trip,
                        dispatch_settings,
                    )
                    person.update(
                        search_active=True,
                        search_radius_miles=float(clock["search_radius_miles"]),
                        initial_search_radius_miles=float(clock["initial_radius_miles"]),
                        max_search_radius_miles=float(clock["max_radius_miles"]),
                        search_radius_capped=bool(clock["radius_capped"]),
                    )
                else:
                    person.update(search_active=False)
                if location:
                    person.update(latitude=location.latitude, longitude=location.longitude,
                                  location_kind="Last reported passenger position", recorded_at=iso_utc(location.received_at))
                else:
                    person.update(latitude=trip.pickup_latitude, longitude=trip.pickup_longitude,
                                  location_kind="Trip pickup (not live passenger GPS)", recorded_at=iso_utc(trip.requested_at))
        people.append(person)
    # Account-less demo trips still represent passengers on the platform.
    for trip in Trip.query.filter(Trip.passenger_id.is_(None), Trip.status.in_(ACTIVE_TRIP_STATES)).all():
        guest = {"key": f"guest-trip:{trip.id}", "id": None, "role": "PASSENGER", "name": trip.passenger_name,
                 "status": trip.status, "trip_id": trip.id, "latitude": trip.pickup_latitude,
                 "longitude": trip.pickup_longitude, "location_kind": "Trip pickup (not live passenger GPS)",
                 "recorded_at": iso_utc(trip.requested_at)}
        if trip.status in {"REQUESTED", "OFFERED"}:
            clock = current_dispatch_expansion(
                trip,
                dispatch_settings,
            )
            guest.update(
                search_active=True,
                search_radius_miles=float(clock["search_radius_miles"]),
                initial_search_radius_miles=float(clock["initial_radius_miles"]),
                max_search_radius_miles=float(clock["max_radius_miles"]),
                search_radius_capped=bool(clock["radius_capped"]),
            )
        else:
            guest["search_active"] = False
        people.append(guest)
    return {"people": people, "server_time": iso_utc(datetime.now(timezone.utc))}


def publish_platform_map():
    socketio.emit("admin_platform_map", platform_snapshot(), room="admin:live")


def randomize_drivers(latitude, longitude, radius_miles):
    # Save the whole operation together; never seed or change online status.
    drivers = Driver.query.order_by(Driver.id).populate_existing().with_for_update().all()
    active_ids = {row[0] for row in db.session.query(Trip.driver_id).filter(
        Trip.driver_id.is_not(None), Trip.status.in_(["DRIVER_ASSIGNED", "DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "PICKUP_PENDING", "IN_PROGRESS"])).all()}
    updated, skipped = [], []
    lat1, lng1 = math.radians(latitude), math.radians(longitude)
    for driver in drivers:
        if driver.id in active_ids or (driver.is_online and not driver.is_available):
            skipped.append(driver.id)
            continue
        angular = radius_miles * math.sqrt(random.random()) / 3958.7613
        bearing = random.uniform(0, 2 * math.pi)
        lat2 = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(bearing))
        lng2 = lng1 + math.atan2(math.sin(bearing) * math.sin(angular) * math.cos(lat1), math.cos(angular) - math.sin(lat1) * math.sin(lat2))
        driver.current_latitude = math.degrees(lat2)
        driver.current_longitude = (math.degrees(lng2) + 180) % 360 - 180
        driver.last_location_at = datetime.now(timezone.utc)
        updated.append(driver)
    db.session.commit()
    for driver in updated:
        socketio.emit("driver_location", {"driver_id": driver.id, "latitude": driver.current_latitude,
                      "longitude": driver.current_longitude, "recorded_at": iso_utc(driver.last_location_at)}, room=f"driver:{driver.id}")
    publish_platform_map()
    return {"ok": True, "updated_driver_ids": [d.id for d in updated], "skipped_driver_ids": skipped}
