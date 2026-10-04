import json
import math
from datetime import datetime, timezone

from app.extensions import db, socketio
from .models import Driver, Vehicle


TEST_DRIVERS = [
    {
        "email": "rex@example.local",
        "name": "Rex",
        "lat": 33.7202,
        "lng": -116.2170,
        "vehicle": ("Toyota", "Prius", 2022, "Silver", "REX001", "CA"),
    },
    {
        "email": "driver2@example.local",
        "name": "Jordan Demo",
        "lat": 33.7280,
        "lng": -116.2240,
        "vehicle": ("Honda", "Civic", 2021, "Blue", "TEST102", "CA"),
    },
    {
        "email": "driver3@example.local",
        "name": "Taylor Demo",
        "lat": 33.7100,
        "lng": -116.2060,
        "vehicle": ("Hyundai", "Elantra", 2023, "White", "TEST103", "CA"),
    },
    {
        "email": "driver4@example.local",
        "name": "Morgan Demo",
        "lat": 33.7390,
        "lng": -116.2400,
        "vehicle": ("Kia", "Niro", 2022, "Black", "TEST104", "CA"),
    },
    {
        "email": "driver5@example.local",
        "name": "Casey Demo",
        "lat": 33.7000,
        "lng": -116.2500,
        "vehicle": ("Ford", "Escape", 2020, "Gray", "TEST105", "CA"),
    },
]


def ensure_test_drivers():
    result = []
    for item in TEST_DRIVERS:
        driver = Driver.query.filter_by(email=item["email"]).first()
        if driver is None:
            driver = Driver(
                display_name=item["name"],
                email=item["email"],
                verification_status="APPROVED",
                is_test_driver=True,
                is_online=True,
                is_available=True,
                current_latitude=item["lat"],
                current_longitude=item["lng"],
                last_location_at=datetime.now(timezone.utc),
            )
            db.session.add(driver)
            db.session.flush()
            make, model, year, color, plate, plate_state = item["vehicle"]
            db.session.add(Vehicle(
                driver_id=driver.id,
                make=make, model=model, year=year, color=color,
                plate=plate, plate_state=plate_state, passenger_capacity=4,
            ))
        else:
            driver.display_name = item["name"]
            driver.verification_status = "APPROVED"
            driver.is_test_driver = True

            # Persistent demo rows can be left offline/unavailable after a
            # previous test run. Restore demo availability unless the driver
            # is genuinely assigned to an active trip.
            from app.trips.models import Trip

            active_assignment = (
                Trip.query
                .filter(
                    Trip.driver_id == driver.id,
                    Trip.status.in_(
                        [
                            "DRIVER_ASSIGNED",
                            "DRIVER_EN_ROUTE",
                            "DRIVER_ARRIVED",
                            "PICKUP_PENDING",
                            "IN_PROGRESS",
                        ]
                    ),
                )
                .first()
            )

            driver.is_online = True
            driver.is_available = (
                active_assignment is None
            )

            if driver.current_latitude is None:
                driver.current_latitude = item["lat"]
            if driver.current_longitude is None:
                driver.current_longitude = item["lng"]
            if driver.last_location_at is None:
                driver.last_location_at = datetime.now(timezone.utc)
        result.append(driver)
    db.session.commit()
    return result


def ensure_test_driver():
    drivers = ensure_test_drivers()
    return drivers[0] if drivers else None


def get_demo_driver():
    return Driver.query.filter_by(email="rex@example.local").first()


def get_rex_driver():
    return Driver.query.filter_by(email="rex@example.local").first()


def get_test_drivers():
    return Driver.query.filter_by(is_test_driver=True).order_by(Driver.id.asc()).all()


def update_driver_location(
    driver_id,
    latitude,
    longitude,
    emit=True,
):
    """
    Backward-compatible wrapper around the common location service.

    Demo and production use the same database write path.
    """
    from app.location.driver_location import set_driver_location

    return set_driver_location(
        driver_id,
        latitude,
        longitude,
        source="legacy_driver_service",
        emit=emit,
    )


def reset_test_drivers():
    updated = []
    for seed in TEST_DRIVERS:
        driver = Driver.query.filter_by(email=seed["email"]).first()
        if not driver:
            continue
        driver.is_online = True
        driver.is_available = True
        driver.current_latitude = seed["lat"]
        driver.current_longitude = seed["lng"]
        driver.last_location_at = datetime.now(timezone.utc)
        updated.append(driver)
    db.session.commit()
    for driver in updated:
        socketio.emit("driver_location", {
            "driver_id": driver.id, "driver_name": driver.display_name,
            "latitude": driver.current_latitude, "longitude": driver.current_longitude,
            "recorded_at": driver.last_location_at.isoformat(),
        }, room=f"driver:{driver.id}")
    from app.admin.platform_map import publish_platform_map
    publish_platform_map()
    return updated


def simulate_test_driver_step(step):
    drivers = get_test_drivers()
    moved = []
    for index, driver in enumerate(drivers):
        # Small deterministic orbit around each driver's current area.
        angle = (int(step) * 0.28) + (index * 1.17)
        radius = 0.0012 + (index * 0.00015)
        lat = float(driver.current_latitude or TEST_DRIVERS[index]["lat"]) + math.sin(angle) * radius
        lng = float(driver.current_longitude or TEST_DRIVERS[index]["lng"]) + math.cos(angle) * radius
        driver.current_latitude = lat
        driver.current_longitude = lng
        driver.last_location_at = datetime.now(timezone.utc)
        moved.append(driver)
    db.session.commit()
    payloads=[]
    for driver in moved:
        payload={
            "driver_id": driver.id, "driver_name": driver.display_name,
            "latitude": driver.current_latitude, "longitude": driver.current_longitude,
            "recorded_at": driver.last_location_at.isoformat(),
        }
        payloads.append(payload)
        socketio.emit("driver_location", payload, room=f"driver:{driver.id}")
        socketio.emit("admin_driver_location", payload)
    from app.admin.platform_map import publish_platform_map
    publish_platform_map()
    return payloads


def haversine_miles(lat1, lng1, lat2, lng2):
    radius_miles = 3958.7613
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def available_drivers_ranked(
    pickup_latitude,
    pickup_longitude,
):
    """
    Authoritative live dispatch candidate query.

    A driver belongs in passenger search calculations when the driver is:

        1. online
        2. APPROVED
        3. has a current location
        4. is NOT actually assigned to another active trip

    `Driver.is_available` is repaired from the real active-trip state instead
    of being trusted as the source of truth. This prevents stale availability
    flags from silently excluding drivers who are physically in range.
    """
    from app.trips.models import Trip

    active_assignment_statuses = {
        "DRIVER_ASSIGNED",
        "DRIVER_EN_ROUTE",
        "DRIVER_ARRIVED",
        "PICKUP_PENDING",
        "IN_PROGRESS",
    }

    busy_driver_ids = {
        int(row[0])
        for row in (
            db.session.query(
                Trip.driver_id
            )
            .filter(
                Trip.driver_id.is_not(None),
                Trip.status.in_(
                    active_assignment_statuses
                ),
            )
            .all()
        )
    }

    drivers = (
        Driver.query
        .filter(
            Driver.is_online.is_(True),
            Driver.verification_status
            == "APPROVED",
        )
        .order_by(
            Driver.id.asc()
        )
        .populate_existing()
        .all()
    )

    ranked = []
    repaired = False

    for driver in drivers:
        actually_available = (
            int(driver.id)
            not in busy_driver_ids
        )

        if (
            bool(driver.is_available)
            != actually_available
        ):
            old_value = bool(
                driver.is_available
            )

            driver.is_available = (
                actually_available
            )

            repaired = True

            print(
                "[DRIVER AVAILABILITY REPAIRED] "
                f"driver={driver.id} "
                f"old={old_value} "
                f"new={actually_available} "
                f"busy={not actually_available}",
                flush=True,
            )

        if not actually_available:
            continue

        if (
            driver.current_latitude is None
            or driver.current_longitude is None
        ):
            print(
                "[DRIVER SEARCH SKIP] "
                f"driver={driver.id} "
                "reason=no_location",
                flush=True,
            )
            continue

        distance_miles = haversine_miles(
            float(pickup_latitude),
            float(pickup_longitude),
            float(driver.current_latitude),
            float(driver.current_longitude),
        )

        ranked.append({
            "driver": driver,
            "distance_miles":
                distance_miles,
        })

    if repaired:
        db.session.flush()

    ranked.sort(
        key=lambda item: (
            float(
                item["distance_miles"]
            ),
            int(
                item["driver"].id
            ),
        )
    )

    print(
        "[DRIVER SEARCH CANDIDATES] "
        f"online_approved={len(drivers)} "
        f"busy={len(busy_driver_ids)} "
        f"eligible_with_location={len(ranked)}",
        flush=True,
    )

    return ranked



def build_driver_preview_route(driver, trip):
    """
    Build a driver preview that includes:

    1. the driver's route to the passenger pickup; and
    2. the passenger's trip route from pickup to destination.

    Privacy rule:
    the driver UI should not render a passenger marker. The pickup point is
    represented only as the join between the two route segments.
    """
    pickup_route = get_driver_pickup_route(
        driver,
        trip,
    )

    trip_geometry = {}

    if trip.route_geometry_json:
        try:
            trip_geometry = json.loads(
                trip.route_geometry_json
            )
        except Exception:
            trip_geometry = {}

    preview_geometry = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "segment": "to_pickup",
                    "label": "Driver to pickup",
                },
                "geometry":
                    pickup_route["geometry"],
            },
        ],
    }

    if trip_geometry:
        preview_geometry["features"].append(
            {
                "type": "Feature",
                "properties": {
                    "segment": "trip_route",
                    "label": "Passenger trip",
                },
                "geometry":
                    trip_geometry,
            }
        )

    return {
        "pickup_route": pickup_route,
        "trip_route": {
            "distance_meters":
                trip.estimated_distance_meters,
            "duration_seconds":
                trip.estimated_duration_seconds,
            "geometry":
                trip_geometry,
        },
        "preview_geometry":
            preview_geometry,
        "destination": {
            "latitude":
                trip.destination_latitude,
            "longitude":
                trip.destination_longitude,
        },
        "pickup_location_hidden":
            True,
    }


def get_driver_pickup_route(driver, trip):
    from app.maps.services import get_driving_route

    if driver.current_latitude is None or driver.current_longitude is None:
        raise ValueError("Driver does not have a current location")

    return get_driving_route(
        driver.current_latitude,
        driver.current_longitude,
        trip.pickup_latitude,
        trip.pickup_longitude,
    )


def route_simulation_points(route_geometry, max_points=90):
    coordinates = route_geometry.get("coordinates", [])
    if not coordinates:
        return []

    if len(coordinates) <= max_points:
        selected = coordinates
    else:
        step = max(1, len(coordinates) // max_points)
        selected = coordinates[::step]

        if selected[-1] != coordinates[-1]:
            selected.append(coordinates[-1])

    return [
        {
            "latitude": float(lat),
            "longitude": float(lng),
        }
        for lng, lat in selected
    ]



def ensure_driver_profile_for_user(user):
    """
    Ensure a User with role DRIVER also has a Driver domain profile.

    Driver signup initially creates a PENDING, offline, unavailable driver.
    Approval/document processing can activate the driver later.
    """
    if user is None or str(user.role).upper() != "DRIVER":
        return None

    driver = Driver.query.filter_by(email=user.email).first()

    if driver is None:
        driver = Driver(
            display_name=user.display_name,
            email=user.email,
            verification_status="PENDING",
            is_test_driver=False,
            is_online=False,
            is_available=False,
        )
        db.session.add(driver)
    else:
        # Keep account/profile display information synchronized.
        driver.display_name = user.display_name

    return driver


def sync_driver_profiles_from_users():
    """
    Repair older DRIVER signups that exist in users but not drivers.

    This is intentionally idempotent and can safely run on startup or when
    loading the Admin dashboard.
    """
    from app.users.models import User

    users = (
        User.query
        .filter(User.role == "DRIVER")
        .order_by(User.id.asc())
        .all()
    )

    changed = False

    for user in users:
        existing = Driver.query.filter_by(email=user.email).first()

        if existing is None:
            ensure_driver_profile_for_user(user)
            changed = True
        elif existing.display_name != user.display_name:
            existing.display_name = user.display_name
            changed = True

    if changed:
        db.session.commit()

    return (
        Driver.query
        .order_by(Driver.id.asc())
        .all()
    )
