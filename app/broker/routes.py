import json
import logging

from flask import Blueprint, jsonify, current_app

from app.extensions import db

from app.trips.stream import publish_trip_snapshot
from app.trips.models import Trip
from app.drivers.models import Driver
from app.drivers.services import get_driver_pickup_route

from .models import SimulationJob
from .services import (
    create_or_reset_job,
    pause_job,
    serialize_job,
    start_job,
)

bp = Blueprint("broker", __name__)
log = logging.getLogger("rideshare.broker_routes")


@bp.post("/trips/<int:trip_id>/drivers/<int:driver_id>/prepare")
def prepare_simulation(trip_id, driver_id):
    if not current_app.config.get("DEMO_MODE"):
        return jsonify({
            "error":
                "Demo motion is disabled. Production mode expects real location updates.",
        }), 409

    log.info(
        "[SIM PREPARE] trip=%s driver=%s",
        trip_id,
        driver_id,
    )

    trip = db.session.get(
        Trip,
        trip_id,
    )

    driver = db.session.get(
        Driver,
        driver_id,
    )

    if trip is None:
        return jsonify({
            "error": "Trip not found",
        }), 404

    if driver is None:
        return jsonify({
            "error": "Driver not found",
        }), 404

    if trip.driver_id != driver.id:
        return jsonify({
            "error": "Trip is not assigned to this driver",
        }), 403

    existing = SimulationJob.query.filter_by(
        trip_id=trip.id,
        driver_id=driver.id,
    ).first()

    # PREVIEW MUST NOT reset a running/paused/ready job. Older behavior called
    # create_or_reset_job() every time Preview was clicked, which could change
    # a RUNNING job back to READY and make the broker appear to stop.
    if (
        existing is not None
        and existing.status in {
            "READY",
            "RUNNING",
            "PAUSED",
        }
    ):
        try:
            route = get_driver_pickup_route(
                driver,
                trip,
            )
        except ValueError as exc:
            return jsonify({
                "error": str(exc),
            }), 409

        log.info(
            "[SIM PREPARE REUSE] job=%s trip=%s driver=%s status=%s index=%s",
            existing.id,
            trip.id,
            driver.id,
            existing.status,
            existing.current_index,
        )

        return jsonify({
            "ok": True,
            "reused": True,
            "job": serialize_job(existing),
            "route": route,
        })

    try:
        job, route = create_or_reset_job(
            trip_id,
            driver_id,
        )
    except ValueError as exc:
        log.warning(
            "[SIM PREPARE FAILED] trip=%s driver=%s error=%s",
            trip_id,
            driver_id,
            exc,
        )
        return jsonify({
            "error": str(exc),
        }), 409

    publish_trip_snapshot(
        trip_id,
        reason="SIMULATION_PREPARED",
    )

    return jsonify({
        "ok": True,
        "reused": False,
        "job": serialize_job(job),
        "route": route,
    })


@bp.post("/trips/<int:trip_id>/drivers/<int:driver_id>/start")
def start_simulation(trip_id, driver_id):
    if not current_app.config.get("DEMO_MODE"):
        return jsonify({
            "error":
                "Demo motion is disabled. Production mode expects real location updates.",
        }), 409

    log.info(
        "[SIM START] trip=%s driver=%s",
        trip_id,
        driver_id,
    )

    try:
        job = start_job(
            trip_id,
            driver_id,
        )
    except ValueError as exc:
        log.warning(
            "[SIM START FAILED] trip=%s driver=%s error=%s",
            trip_id,
            driver_id,
            exc,
        )
        return jsonify({
            "error": str(exc),
        }), 409

    from app.trips.notices import (
        record_passenger_notice,
    )

    if job.phase == "TO_DESTINATION":
        notice_kind = "DROPOFF_DRIVE_STARTED"
        notice_message = (
            "The driver started the trip to your drop-off."
        )
    else:
        notice_kind = "PICKUP_DRIVE_STARTED"
        notice_message = (
            "The driver started driving toward your pickup."
        )

    record_passenger_notice(
        trip_id,
        notice_kind,
        notice_message,
        payload={
            "simulation_job_id": job.id,
            "phase": job.phase,
        },
        emit=True,
    )

    publish_trip_snapshot(
        trip_id,
        reason="SIMULATION_STARTED",
    )

    return jsonify({
        "ok": True,
        "job": serialize_job(job),
    })


@bp.post("/trips/<int:trip_id>/drivers/<int:driver_id>/pause")
def pause_simulation(trip_id, driver_id):
    if not current_app.config.get("DEMO_MODE"):
        return jsonify({
            "error":
                "Demo motion is disabled. Production mode expects real location updates.",
        }), 409

    log.info(
        "[SIM PAUSE] trip=%s driver=%s",
        trip_id,
        driver_id,
    )

    try:
        job = pause_job(
            trip_id,
            driver_id,
        )
    except ValueError as exc:
        log.warning(
            "[SIM PAUSE FAILED] trip=%s driver=%s error=%s",
            trip_id,
            driver_id,
            exc,
        )
        return jsonify({
            "error": str(exc),
        }), 409

    publish_trip_snapshot(
        trip_id,
        reason="SIMULATION_PAUSED",
    )

    return jsonify({
        "ok": True,
        "job": serialize_job(job),
    })


@bp.get("/trips/<int:trip_id>")
def simulation_status(trip_id):
    # Retained for debugging/admin inspection. Driver/passenger live updates
    # do not use this GET endpoint.
    job = SimulationJob.query.filter_by(
        trip_id=trip_id
    ).first()

    return jsonify({
        "job": serialize_job(job),
    })
