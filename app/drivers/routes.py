from flask import Blueprint, jsonify, request, current_app

from .models import Driver
from .services import get_demo_driver, get_test_drivers, update_driver_location

bp = Blueprint("drivers", __name__)


def serialize_driver(driver):
    vehicle = driver.vehicles[0] if driver.vehicles else None

    return {
        "id": driver.id,
        "name": driver.display_name,
        "email": driver.email,
        "verification_status": driver.verification_status,
        "is_test_driver": driver.is_test_driver,
        "is_online": driver.is_online,
        "is_available": driver.is_available,
        "current_latitude": driver.current_latitude,
        "current_longitude": driver.current_longitude,
        "last_location_at": (
            driver.last_location_at.isoformat()
            if driver.last_location_at else None
        ),
        "fare_increase_accept_count": int(
            driver.fare_increase_accept_count
            or 0
        ),
        "last_fare_increase_accept_at": (
            driver.last_fare_increase_accept_at.isoformat()
            if driver.last_fare_increase_accept_at
            else None
        ),
        "vehicle": {
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "color": vehicle.color,
            "plate": vehicle.plate,
            "plate_state": vehicle.plate_state,
        } if vehicle else None,
    }


@bp.get("/demo")
def demo_driver():
    driver = get_demo_driver()
    return jsonify({
        "driver": serialize_driver(driver),
        "vehicle": serialize_driver(driver)["vehicle"],
    })


@bp.get("/test")
def test_drivers():
    return jsonify([
        serialize_driver(driver)
        for driver in get_test_drivers()
    ])


@bp.get("/<int:driver_id>")
def driver_detail(driver_id):
    driver = Driver.query.get_or_404(driver_id)
    return jsonify(serialize_driver(driver))


@bp.post("/<int:driver_id>/location")
@bp.post("/<int:driver_id>/location")
def update_location(driver_id):
    data = request.get_json(force=True)

    from app.location.providers.gps import (
        submit_gps_driver_location,
    )

    result = submit_gps_driver_location(
        driver_id,
        data["latitude"],
        data["longitude"],
    )

    driver = result.driver

    if driver is None:
        return jsonify({
            "error": "Driver not found",
        }), 404

    return jsonify({
        "ok": True,
        "driver_id": driver.id,
        "latitude": driver.current_latitude,
        "longitude": driver.current_longitude,
        "provider": "gps",
        "affected_trip_ids": [
            int(event["trip_id"])
            for event in result.proximity_events
        ],
    })


@bp.get("/<int:driver_id>/trips/<int:trip_id>/pickup-route")
@bp.get("/<int:driver_id>/trips/<int:trip_id>/pickup-route")
def pickup_route(driver_id, trip_id):
    """
    Driver preview route.

    This route can be previewed when:
      - the trip is already assigned to the driver; or
      - the driver has an existing RideOffer row for the trip.

    The response includes the route to pickup and the passenger's trip route,
    but the pickup point itself should remain visually hidden in the driver UI.
    """
    from app.trips.models import Trip, RideOffer
    from .models import Driver
    from .services import (
        build_driver_preview_route,
        route_simulation_points,
    )

    driver = Driver.query.get_or_404(driver_id)
    trip = Trip.query.get_or_404(trip_id)

    offer = (
        RideOffer.query
        .filter_by(
            trip_id=trip.id,
            driver_id=driver.id,
        )
        .first()
    )

    can_preview = (
        trip.driver_id == driver.id
        or offer is not None
    )

    if not can_preview:
        return jsonify({
            "error":
                "This trip is not currently visible to this driver",
        }), 403

    try:
        preview = build_driver_preview_route(
            driver,
            trip,
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
        }), 409

    return jsonify({
        "driver_id": driver.id,
        "trip_id": trip.id,
        "offer_status": (
            offer.status
            if offer is not None
            else "ASSIGNED"
        ),
        "preview": preview,
        "simulation_points":
            route_simulation_points(
                preview["pickup_route"]["geometry"]
            ),
    })


@bp.get("/<int:driver_id>/active-trip")
def active_trip(driver_id):
    from app.trips.models import Trip

    trip = (
        Trip.query
        .filter(
            Trip.driver_id == driver_id,
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
        .order_by(Trip.accepted_at.desc())
        .first()
    )

    if trip is None:
        return jsonify({"active": False})

    return jsonify({
        "active": True,
        "trip_id": trip.id,
        "status": trip.status,
    })


@bp.post("/<int:driver_id>/demo-location")
@bp.post("/<int:driver_id>/demo-location")
@bp.post("/<int:driver_id>/demo-location")
def demo_location(driver_id):
    """
    Demo provider endpoint.

    Only coordinate acquisition is demo-specific. The provider feeds the same
    shared location-ingestion pipeline used by production GPS.
    """
    import math

    from app.extensions import db
    from app.location.providers.demo import (
        submit_demo_driver_location,
    )
    from app.trips.models import Trip, RideOffer
    from app.dispatch.radius import (
        current_dispatch_expansion,
    )
    from app.admin.settings import (
        get_dispatch_settings,
    )

    if not current_app.config.get(
        "DEMO_MODE"
    ):
        return jsonify({
            "error":
                "Map positioning is only available in demo mode",
        }), 403

    driver = (
        Driver.query
        .filter_by(id=driver_id)
        .populate_existing()
        .first()
    )

    if driver is None:
        return jsonify({
            "error": "Driver not found",
        }), 404

    active_assignment = (
        Trip.query
        .filter(
            Trip.driver_id == driver_id,
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

    if active_assignment is not None:
        return jsonify({
            "error":
                "Finish the current trip before changing demo location",
        }), 409

    data = request.get_json(
        silent=True
    ) or {}

    try:
        latitude = float(
            data["latitude"]
        )
        longitude = float(
            data["longitude"]
        )

        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise ValueError()

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return jsonify({
            "error":
                "Valid latitude and longitude are required",
        }), 400

    result = submit_demo_driver_location(
        driver_id,
        latitude,
        longitude,
    )

    driver = result.driver

    if driver is None:
        return jsonify({
            "error": "Driver not found",
        }), 404

    settings = get_dispatch_settings()
    memberships = []

    active_searches = (
        Trip.query
        .filter(
            Trip.status.in_(
                [
                    "REQUESTED",
                    "OFFERED",
                ]
            )
        )
        .order_by(
            Trip.id.asc()
        )
        .all()
    )

    for trip in active_searches:
        offer = (
            RideOffer.query
            .filter_by(
                trip_id=trip.id,
                driver_id=driver_id,
            )
            .populate_existing()
            .first()
        )

        clock = current_dispatch_expansion(
            trip,
            settings,
        )

        memberships.append({
            "trip_id": trip.id,
            "status": (
                offer.status
                if offer
                else "NO_ROW"
            ),
            "distance_miles": (
                round(
                    float(
                        offer.distance_miles
                    ),
                    3,
                )
                if offer
                else None
            ),
            "search_radius_miles":
                round(
                    float(
                        clock[
                            "search_radius_miles"
                        ]
                    ),
                    3,
                ),
            "rank": (
                int(offer.rank)
                if offer
                else None
            ),
            "in_active_queue":
                bool(
                    offer
                    and offer.status
                    == "OFFERED"
                ),
        })

    return jsonify({
        "ok": True,
        "driver_id": driver.id,
        "latitude":
            driver.current_latitude,
        "longitude":
            driver.current_longitude,
        "provider":
            "demo_map",
        "saved_to_database":
            True,
        "dispatch_marked_due":
            True,
        "affected_trip_ids": [
            int(event["trip_id"])
            for event in result.proximity_events
        ],
        "queue_memberships":
            memberships,
    })


@bp.post("/<int:driver_id>/availability")
@bp.post("/<int:driver_id>/availability")
def set_availability(driver_id):
    from app.extensions import db, socketio
    from app.trips.models import Trip
    from app.dispatch.collision import (
        mark_active_searches_collision_dirty,
    )

    data = request.get_json(
        silent=True
    ) or {}

    if type(
        data.get("is_online")
    ) is not bool:
        return jsonify({
            "error":
                "is_online must be true or false"
        }), 400

    driver = (
        Driver.query
        .filter_by(id=driver_id)
        .populate_existing()
        .with_for_update()
        .first()
    )

    if driver is None:
        return jsonify({
            "error": "Driver not found"
        }), 404

    online = data["is_online"]

    if (
        online
        and driver.verification_status
        != "APPROVED"
    ):
        return jsonify({
            "error":
                "Driver approval is required to go online"
        }), 403

    active_assignment = (
        Trip.query
        .filter(
            Trip.driver_id
            == driver_id,
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

    driver.is_online = online
    driver.is_available = (
        online
        and active_assignment
        is None
    )

    db.session.commit()

    # Search membership is recalculated only by the collision lane.
    mark_active_searches_collision_dirty(
        (
            f"DRIVER_AVAILABILITY:"
            f"{driver_id}:"
            f"{int(bool(online))}"
        )
    )

    from app.admin.platform_map import (
        publish_platform_map,
    )

    publish_platform_map()

    payload = serialize_driver(
        driver
    )

    socketio.emit(
        "driver_availability",
        payload,
        room=f"driver:{driver_id}",
    )

    return jsonify(payload)
