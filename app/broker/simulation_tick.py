from sqlalchemy import or_

from app.extensions import db
from app.trips.models import Trip
from .models import SimulationJob
from .services import (
    validate_job_for_advance,
)
from .demo_service import (
    advance_demo_job_by_id,
)
from app.dispatch.timing import utcnow


def due_simulation_job_ids():
    """
    Read-only simulation lane query.

    It never examines passenger search/radius state.
    """
    now = utcnow()

    return [
        int(row[0])
        for row in (
            db.session.query(
                SimulationJob.id
            )
            .filter(
                SimulationJob.status
                == "RUNNING",
                or_(
                    SimulationJob.next_due_at
                    .is_(None),
                    SimulationJob.next_due_at
                    <= now,
                ),
            )
            .order_by(
                SimulationJob.next_due_at.asc(),
                SimulationJob.id.asc(),
            )
            .all()
        )
    ]


def run_simulation_step(
    job_id,
):
    if not validate_job_for_advance(
        job_id
    ):
        return None

    trip_id = (
        advance_demo_job_by_id(
            job_id
        )
    )

    if not trip_id:
        return None

    job = db.session.get(
        SimulationJob,
        int(job_id),
    )

    trip = db.session.get(
        Trip,
        int(trip_id),
    )

    if job is None or trip is None:
        return None

    return {
        "trip_id": int(trip.id),
        "driver_id": int(job.driver_id),
        "job_id": int(job.id),
        "phase": job.phase,
        "job_status": job.status,
        "trip_status": trip.status,
        "progress_percent":
            float(
                job.progress_percent
                or 0.0
            ),
        "eta_seconds":
            trip.driver_eta_seconds,
        "next_due_at": (
            job.next_due_at.isoformat()
            if job.next_due_at
            else None
        ),
    }
