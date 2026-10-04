import json
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.drivers.models import Driver
from app.trips.models import Trip

from .models import SimulationJob


PICKUP_START_STATES = {
    "DRIVER_ASSIGNED",
    "DRIVER_EN_ROUTE",
}

TERMINAL_TRIP_STATES = {
    "CANCELED",
    "COMPLETED",
}


def utcnow():
    return datetime.now(timezone.utc)


def get_trip_driver(
    trip_id,
    driver_id,
    *,
    lock=False,
):
    """
    Normal broker lookup/validation helper.

    This contains business validation shared by demo now and any future
    production motion implementation.
    """
    trip_query = (
        Trip.query
        .filter_by(id=int(trip_id))
    )

    driver_query = (
        Driver.query
        .filter_by(id=int(driver_id))
    )

    if lock:
        trip_query = (
            trip_query.with_for_update()
        )
        driver_query = (
            driver_query.with_for_update()
        )

    trip = trip_query.first()
    driver = driver_query.first()

    if trip is None:
        raise ValueError(
            "Trip not found"
        )

    if driver is None:
        raise ValueError(
            "Driver not found"
        )

    if trip.driver_id != driver.id:
        raise ValueError(
            "Trip is not assigned to this driver"
        )

    return trip, driver


def validate_pickup_prepare(
    trip,
    driver,
):
    """
    Normal validation for preparing driver -> passenger travel.
    """
    if trip.status not in {
        "DRIVER_ASSIGNED",
        "DRIVER_EN_ROUTE",
    }:
        raise ValueError(
            "Pickup route cannot be prepared in the current trip state"
        )

    if (
        driver.current_latitude is None
        or driver.current_longitude is None
    ):
        raise ValueError(
            "Driver does not have a current location"
        )


def validate_destination_prepare(
    trip,
    driver,
):
    """
    Normal validation for preparing passenger + driver -> destination travel.
    """
    if trip.pickup_confirmed_at is None:
        raise ValueError(
            "Passenger must confirm pickup before the driver can continue"
        )

    if trip.status != "IN_PROGRESS":
        print(
            "[DESTINATION PREP STATE REPAIR] "
            f"trip={trip.id} "
            f"old_status={trip.status} "
            "new_status=IN_PROGRESS",
            flush=True,
        )
        trip.status = "IN_PROGRESS"
        db.session.flush()

    if (
        driver.current_latitude is None
        or driver.current_longitude is None
    ):
        raise ValueError(
            "Driver does not have a current location"
        )


def validate_start_permission(
    trip,
    job,
):
    """
    Normal business rule gate for Start Driving / Continue Ride.
    """
    if (
        trip.status == "PICKUP_PENDING"
        and trip.pickup_confirmed_at
        is None
    ):
        raise ValueError(
            "Passenger must confirm pickup before the driver can continue"
        )

    if (
        trip.pickup_confirmed_at
        is not None
        and trip.status
        == "PICKUP_PENDING"
    ):
        trip.status = "IN_PROGRESS"
        db.session.flush()

    if trip.status in TERMINAL_TRIP_STATES:
        raise ValueError(
            "This trip can no longer be driven"
        )

    if job.phase == "TO_DESTINATION":
        if trip.pickup_confirmed_at is None:
            raise ValueError(
                "Passenger must confirm pickup before the driver can continue"
            )

        if trip.status != "IN_PROGRESS":
            trip.status = "IN_PROGRESS"
            db.session.flush()

    elif job.phase == "TO_PICKUP":
        if (
            trip.status
            not in PICKUP_START_STATES
        ):
            raise ValueError(
                "Pickup drive cannot start in the current trip state"
            )

    else:
        raise ValueError(
            f"Unknown broker phase: {job.phase}"
        )

    points = json.loads(
        job.route_points_json
    )

    if not points:
        raise ValueError(
            "Motion route contains no movement points"
        )

    if (
        job.current_index
        >= len(points)
    ):
        raise ValueError(
            "Motion phase is already complete"
        )

    return points


def create_or_reset_job(
    trip_id,
    driver_id,
):
    """
    Normal validated entry point for preparing phase 1.

    The demo service creates the simulated route/motion data only after this
    normal service approves the request.
    """
    trip, driver = get_trip_driver(
        trip_id,
        driver_id,
        lock=True,
    )

    validate_pickup_prepare(
        trip,
        driver,
    )

    job = (
        SimulationJob.query
        .filter_by(
            trip_id=trip.id
        )
        .with_for_update()
        .first()
    )

    from .demo_service import (
        prepare_pickup_motion,
    )

    return prepare_pickup_motion(
        trip,
        driver,
        job=job,
    )


def prepare_destination_job(
    trip_id,
    driver_id,
):
    """
    Normal validated entry point for phase 2.

    Passenger confirmation is checked here, outside the demo motion module.
    """
    trip, driver = get_trip_driver(
        trip_id,
        driver_id,
        lock=True,
    )

    validate_destination_prepare(
        trip,
        driver,
    )

    job = (
        SimulationJob.query
        .filter_by(
            trip_id=trip.id
        )
        .with_for_update()
        .first()
    )

    from .demo_service import (
        prepare_destination_motion,
    )

    return prepare_destination_motion(
        trip,
        driver,
        job=job,
    )


def start_job(
    trip_id,
    driver_id,
):
    """
    Normal state transition for Start Driving / Continue Ride.

    This function validates permission and changes the job to RUNNING.
    It does not move coordinates.
    """
    trip, driver = get_trip_driver(
        trip_id,
        driver_id,
        lock=True,
    )

    job = (
        SimulationJob.query
        .filter_by(
            trip_id=trip.id,
            driver_id=driver.id,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )

    if (
        trip.pickup_confirmed_at
        is not None
        and (
            job is None
            or job.phase
            != "TO_DESTINATION"
            or job.status
            == "COMPLETED"
        )
    ):
        # Passenger confirmation is authoritative. If an older pickup-motion
        # write left trip.status stale, repair it before preparing phase 2.
        if trip.status != "IN_PROGRESS":
            print(
                "[BROKER START STATE REPAIR] "
                f"trip={trip.id} "
                f"old_status={trip.status} "
                "new_status=IN_PROGRESS",
                flush=True,
            )
            trip.status = "IN_PROGRESS"
            db.session.flush()

        job, _ = (
            prepare_destination_job(
                trip.id,
                driver.id,
            )
        )

    elif job is None:
        job, _ = (
            create_or_reset_job(
                trip.id,
                driver.id,
            )
        )

    points = validate_start_permission(
        trip,
        job,
    )

    job.status = "RUNNING"
    job.next_due_at = utcnow()

    if job.started_at is None:
        job.started_at = utcnow()

    job.paused_at = None

    if job.phase == "TO_PICKUP":
        trip.status = "DRIVER_EN_ROUTE"
    else:
        trip.status = "IN_PROGRESS"

    trip.driver_eta_seconds = int(
        max(
            0,
            len(points)
            - job.current_index,
        )
        * float(
            job.step_interval_seconds
        )
    )

    db.session.commit()

    print(
        "[BROKER START VALIDATED] "
        f"job={job.id} "
        f"trip={trip.id} "
        f"driver={driver.id} "
        f"phase={job.phase} "
        f"status={job.status}",
        flush=True,
    )

    return job


def pause_job(
    trip_id,
    driver_id,
):
    """
    Normal validated pause state transition. No coordinate motion here.
    """
    trip, driver = get_trip_driver(
        trip_id,
        driver_id,
        lock=True,
    )

    job = (
        SimulationJob.query
        .filter_by(
            trip_id=trip.id,
            driver_id=driver.id,
        )
        .with_for_update()
        .first()
    )

    if job is None:
        raise ValueError(
            "Simulation job not found"
        )

    if job.status == "RUNNING":
        job.status = "PAUSED"
        job.paused_at = utcnow()
        job.next_due_at = None
        db.session.commit()

    return job


def serialize_job(
    job,
):
    if job is None:
        return None

    return {
        "id": job.id,
        "trip_id": job.trip_id,
        "driver_id": job.driver_id,
        "status": job.status,
        "phase": job.phase,
        "current_index":
            job.current_index,
        "progress_percent":
            round(
                job.progress_percent,
                2,
            ),
        "step_interval_seconds":
            job.step_interval_seconds,
        "route_geometry":
            json.loads(
                job.route_geometry_json
            ),
        "started_at": (
            job.started_at.isoformat()
            if job.started_at
            else None
        ),
        "completed_at": (
            job.completed_at.isoformat()
            if job.completed_at
            else None
        ),
        "next_due_at": (
            job.next_due_at.isoformat()
            if job.next_due_at
            else None
        ),
    }


def get_running_job_ids():
    """
    Normal DB query used by the broker scheduler.
    """
    return [
        row[0]
        for row in (
            db.session.query(
                SimulationJob.id
            )
            .filter(
                SimulationJob.status
                == "RUNNING"
            )
            .order_by(
                SimulationJob.id.asc()
            )
            .all()
        )
    ]


def validate_job_for_advance(
    job_id,
):
    """
    Normal validation executed before the demo motion engine gets one step.

    Returns True when the job is still allowed to move. Invalid jobs are
    stopped here so demo_service.py contains no trip-permission rules.
    """
    job = (
        SimulationJob.query
        .filter_by(id=int(job_id))
        .with_for_update()
        .first()
    )

    if (
        job is None
        or job.status != "RUNNING"
    ):
        db.session.rollback()
        return False

    trip = db.session.get(
        Trip,
        job.trip_id,
    )

    driver = db.session.get(
        Driver,
        job.driver_id,
    )

    if trip is None or driver is None:
        db.session.delete(job)
        db.session.commit()
        return False

    if trip.driver_id != driver.id:
        job.status = "STOPPED"
        job.next_due_at = None
        db.session.commit()
        return False

    if trip.status in TERMINAL_TRIP_STATES:
        job.status = "STOPPED"
        job.next_due_at = None
        db.session.commit()
        return False

    if job.phase == "TO_DESTINATION":
        if trip.pickup_confirmed_at is None:
            job.status = "READY"
            job.next_due_at = None
            db.session.commit()
            return False

        # A valid destination job plus passenger confirmation is authoritative
        # for the active movement phase. Repair stale trip state instead of
        # stopping the scheduler. This prevents a delayed/stale write from
        # freezing the destination simulation.
        if trip.status != "IN_PROGRESS":
            print(
                "[BROKER STATE REPAIR] "
                f"trip={trip.id} "
                f"job={job.id} "
                f"phase={job.phase} "
                f"old_status={trip.status} "
                "new_status=IN_PROGRESS",
                flush=True,
            )

            trip.status = "IN_PROGRESS"
            db.session.commit()

    elif job.phase == "TO_PICKUP":
        if trip.pickup_confirmed_at is not None:
            job.status = "COMPLETED"
            job.next_due_at = None

            if trip.status != "IN_PROGRESS":
                trip.status = "IN_PROGRESS"

            db.session.commit()

            print(
                "[BROKER PICKUP STEP BLOCKED AFTER CONFIRMATION] "
                f"trip={trip.id} "
                f"job={job.id}",
                flush=True,
            )

            return False

        if trip.status not in {
            "DRIVER_ASSIGNED",
            "DRIVER_EN_ROUTE",
        }:
            job.status = "READY"
            job.next_due_at = None
            db.session.commit()
            return False

    else:
        job.status = "ERROR"
        job.next_due_at = None
        db.session.commit()
        return False

    return True


def reconcile_jobs():
    """
    Normal authoritative state validation.

    Keeps demo motion jobs synchronized with the real trip/driver state.
    """
    jobs = (
        SimulationJob.query
        .filter(
            SimulationJob.status.in_(
                [
                    "READY",
                    "RUNNING",
                    "PAUSED",
                ]
            )
        )
        .all()
    )

    changed = False

    for job in jobs:
        trip = db.session.get(
            Trip,
            job.trip_id,
        )

        driver = db.session.get(
            Driver,
            job.driver_id,
        )

        if trip is None or driver is None:
            db.session.delete(job)
            changed = True
            continue

        if trip.driver_id != driver.id:
            job.status = "STOPPED"
            changed = True
            continue

        if trip.status in TERMINAL_TRIP_STATES:
            job.status = "STOPPED"
            changed = True

    if changed:
        db.session.commit()
