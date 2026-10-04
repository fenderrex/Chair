from flask import Blueprint, jsonify, render_template, request, current_app

from app.extensions import db
from app.drivers.services import (
    get_rex_driver,
    reset_test_drivers,
    simulate_test_driver_step,
    update_driver_location,
)
from .services import (
    dashboard_counts,
    recent_trips,
    all_drivers,
    all_passengers,
    active_trip_requests,
    delete_trip,
    delete_driver,
    delete_passenger,
)

from .settings import get_dispatch_settings, save_dispatch_settings

bp = Blueprint("admin", __name__)


@bp.get("/")
def dashboard():
    return render_template(
        "admin.html",
        dispatch_settings=get_dispatch_settings(),
        counts=dashboard_counts(),
        trips=recent_trips(),
        drivers=all_drivers(),
        passengers=all_passengers(),
        active_requests=active_trip_requests(),
    )


@bp.delete("/trips/<int:trip_id>")
def remove_trip(trip_id):
    try:
        delete_trip(trip_id)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Admin trip delete failed for trip %s",
            trip_id,
        )
        return jsonify({
            "error": f"Trip delete failed: {exc}",
        }), 500
    return jsonify({"ok": True, "trip_id": trip_id})


@bp.delete("/drivers/<int:driver_id>")
def remove_driver(driver_id):
    try:
        delete_driver(driver_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True, "driver_id": driver_id})


@bp.delete("/passengers/<int:user_id>")
def remove_passenger(user_id):
    try:
        delete_passenger(user_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True, "user_id": user_id})


@bp.post("/demo/reset-all-drivers")
def reset_all_demo_drivers():
    drivers = reset_test_drivers()
    return jsonify({"ok": True, "reset_driver_ids": [d.id for d in drivers]})


@bp.post("/demo/simulate-step")
def simulate_step():
    data = request.get_json(silent=True) or {}
    step = int(data.get("step", 0))
    return jsonify({"ok": True, "drivers": simulate_test_driver_step(step)})


@bp.post("/demo/rex-location")
def set_rex_location():
    data = request.get_json(force=True)
    rex = get_rex_driver()
    if rex is None:
        return jsonify({"error": "Rex driver not found"}), 404

    driver = update_driver_location(
        rex.id,
        float(data["latitude"]),
        float(data["longitude"]),
    )
    driver.is_online = True
    driver.is_available = True
    db.session.commit()

    return jsonify({
        "ok": True,
        "driver_id": driver.id,
        "driver_name": driver.display_name,
        "latitude": driver.current_latitude,
        "longitude": driver.current_longitude,
    })


@bp.post("/dispatch-settings")
def update_dispatch_settings():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Settings must be a JSON object"}), 400
    try:
        return jsonify(save_dispatch_settings(data))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/demo/randomize-drivers")
def randomize_driver_locations():
    import math
    from .platform_map import randomize_drivers
    if not current_app.config.get("DEMO_MODE"):
        return jsonify({"error": "Randomizing locations requires demo mode"}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A map center and radius are required"}), 400
    try:
        lat, lng, radius = (float(data[key]) for key in ("latitude", "longitude", "radius_miles"))
        if not all(math.isfinite(v) for v in (lat, lng, radius)) or not -90 <= lat <= 90 or not -180 <= lng <= 180 or not .1 <= radius <= 100:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Use a valid map center and radius from 0.1 to 100 miles"}), 400
    return jsonify(randomize_drivers(lat, lng, radius))
