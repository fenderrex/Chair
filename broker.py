import os
import time

import requests

os.environ["BROKER_PROCESS"] = "1"

from app import create_app
from app.extensions import db
from app.dispatch.collision import (
    due_collision_trip_ids,
    run_collision_check,
)
from app.broker.simulation_tick import (
    due_simulation_job_ids,
    run_simulation_step,
)


SIMULATION_TICK_SECONDS = float(
    os.getenv(
        "SIMULATION_TICK_SECONDS",
        "0.10",
    )
)

COLLISION_TICK_SECONDS = float(
    os.getenv(
        "COLLISION_TICK_SECONDS",
        "0.10",
    )
)

IDLE_SLEEP_SECONDS = 0.02

STREAM_URL = os.getenv(
    "TRIP_STREAM_CALLBACK_URL",
    "http://127.0.0.1:5100/trips/internal/stream-publish",
)

BROKER_BUILD = "dual-lane-broker-v1"

BROKER_LOCK_PATH = os.getenv(
    "RIDESHARE_BROKER_LOCK_PATH",
    "/tmp/rideshare_demo_broker.lock",
)

_broker_lock_file = None


def acquire_single_broker_lock():
    global _broker_lock_file

    try:
        import fcntl
    except ImportError:
        return True

    _broker_lock_file = open(
        BROKER_LOCK_PATH,
        "a+",
    )

    try:
        fcntl.flock(
            _broker_lock_file.fileno(),
            fcntl.LOCK_EX
            | fcntl.LOCK_NB,
        )
    except BlockingIOError:
        return False

    _broker_lock_file.seek(0)
    _broker_lock_file.truncate()
    _broker_lock_file.write(
        f"pid={os.getpid()} "
        f"build={BROKER_BUILD}\n"
    )
    _broker_lock_file.flush()

    return True


def broker_log(message):
    print(
        f"[BROKER] {message}",
        flush=True,
    )


def publish_trip_update(
    trip_id,
    reason,
    *,
    new_driver_ids=None,
    notices=None,
):
    payload = {
        "trip_id": int(
            trip_id
        ),
        "reason":
            str(reason),
        "new_driver_ids": [
            int(driver_id)
            for driver_id in (
                new_driver_ids
                or []
            )
        ],
        "notices":
            notices or [],
    }

    try:
        response = requests.post(
            STREAM_URL,
            json=payload,
            timeout=2.0,
        )

        broker_log(
            "STREAM "
            f"trip={trip_id} "
            f"reason={reason} "
            f"http={response.status_code}"
        )

    except Exception as exc:
        broker_log(
            "STREAM FAILED "
            f"trip={trip_id} "
            f"reason={reason} "
            f"error={exc}"
        )


def collision_notices(
    result,
):
    notices = []

    reason = str(
        result.get(
            "trigger_reason",
            "COLLISION_CHECK",
        )
    )

    radius = float(
        result.get(
            "search_radius_miles",
            0.0,
        )
    )

    reviewing = int(
        result.get(
            "reviewing_count",
            0,
        )
    )

    if reason == "RIDER_REQUEST":
        notices.append({
            "kind":
                "SEARCH_STARTED",
            "message":
                "Ride requested. Checking nearby drivers.",
            "payload": {
                "collision_revision":
                    result.get(
                        "collision_revision"
                    ),
            },
        })

    elif reason.startswith(
        "DRIVER_POSITION:"
    ):
        notices.append({
            "kind":
                "DRIVER_POSITION_CHECK",
            "message":
                "A driver position changed. Rechecking your search area.",
            "payload": {
                "trigger": reason,
            },
        })

    elif reason.startswith(
        "DRIVER_AVAILABILITY:"
    ):
        notices.append({
            "kind":
                "DRIVER_AVAILABILITY_CHECK",
            "message":
                "Driver availability changed. Rechecking your search area.",
            "payload": {
                "trigger": reason,
            },
        })

    elif reason == "SEARCH_RADIUS_DUE":
        notices.append({
            "kind":
                "SEARCH_RADIUS_STEP",
            "message":
                f"Search radius is now {radius:.1f} mi. Checking drivers again.",
            "payload": {
                "search_radius_miles":
                    radius,
            },
        })

    elif reason == "FARE_WAIT_DUE":
        notices.append({
            "kind":
                "FARE_WAIT_STEP",
            "message":
                "The current driver-response window ended. Checking the next search step.",
        })

    elif reason == "FARE_ROUND_RESTART":
        notices.append({
            "kind":
                "FARE_ROUND_RESTART",
            "message":
                "The updated fare was accepted. Restarting the driver search.",
        })

    elif reason.startswith(
        "DRIVER_DECLINED:"
    ):
        notices.append({
            "kind":
                "DRIVER_DECLINED",
            "message":
                "A driver declined the ride. Matching is continuing with the remaining drivers.",
            "payload": {
                "trigger": reason,
            },
        })

    if result.get(
        "fare_changed"
    ):
        notices.append({
            "kind":
                "FARE_REVIEW_READY",
            "message":
                "The current search round ended without an acceptance. A fare review is ready.",
        })

    for driver_id in (
        result.get(
            "matched_driver_ids",
            [],
        )
        or []
    ):
        notices.append({
            "kind":
                "DRIVER_MATCHED",
            "message":
                "A driver entered your current search area and can review the fare.",
            "payload": {
                "driver_id":
                    int(driver_id),
            },
        })

    for driver_id in (
        result.get(
            "unmatched_driver_ids",
            [],
        )
        or []
    ):
        notices.append({
            "kind":
                "DRIVER_UNMATCHED",
            "message":
                "A driver left your current search area or became unavailable.",
            "payload": {
                "driver_id":
                    int(driver_id),
            },
        })

    notices.append({
        "kind":
            "COLLISION_CHECK_COMPLETE",
        "message":
            (
                f"Search check complete: "
                f"{reviewing} driver"
                f"{'' if reviewing == 1 else 's'} "
                f"reviewing • radius {radius:.1f} mi."
            ),
        "payload": {
            "search_radius_miles":
                radius,
            "reviewing_count":
                reviewing,
            "collision_revision":
                result.get(
                    "collision_revision"
                ),
        },
    })

    return notices


def simulation_notices(
    result,
):
    phase = result.get(
        "phase"
    )

    progress = float(
        result.get(
            "progress_percent",
            0.0,
        )
    )

    eta = result.get(
        "eta_seconds"
    )

    trip_status = result.get(
        "trip_status"
    )

    eta_text = ""

    if eta is not None:
        eta_text = (
            f" • ETA "
            f"{max(0, int((float(eta) + 59) // 60))} min"
        )

    if phase == "TO_DESTINATION":
        if trip_status == "COMPLETED":
            message = (
                "You reached the drop-off. "
                "The ride is complete."
            )
            kind = "DROPOFF_ARRIVED"
        else:
            message = (
                f"Driving to drop-off — "
                f"{progress:.1f}%"
                f"{eta_text}"
            )
            kind = "DROPOFF_STEP"

    else:
        if trip_status == "DRIVER_ARRIVED":
            message = (
                "Your driver arrived at the pickup point."
            )
            kind = "PICKUP_ARRIVED"
        else:
            message = (
                f"Driver approaching pickup — "
                f"{progress:.1f}%"
                f"{eta_text}"
            )
            kind = "PICKUP_DRIVE_STEP"

    return [{
        "kind": kind,
        "message": message,
        "payload": {
            "job_id":
                result.get(
                    "job_id"
                ),
            "phase":
                phase,
            "progress_percent":
                progress,
            "eta_seconds":
                eta,
            "next_due_at":
                result.get(
                    "next_due_at"
                ),
        },
    }]


def run_collision_lane():
    trip_ids = (
        due_collision_trip_ids()
    )

    for trip_id in trip_ids:
        try:
            result = run_collision_check(
                trip_id
            )

            if result is None:
                continue

            publish_trip_update(
                trip_id,
                "COLLISION_TICK",
                new_driver_ids=
                    result.get(
                        "matched_driver_ids",
                        [],
                    ),
                notices=
                    collision_notices(
                        result
                    ),
            )

        except Exception as exc:
            db.session.rollback()

            broker_log(
                "COLLISION TICK FAILED "
                f"trip={trip_id} "
                f"error={exc}"
            )


def run_simulation_lane():
    job_ids = (
        due_simulation_job_ids()
    )

    for job_id in job_ids:
        try:
            result = run_simulation_step(
                job_id
            )

            if result is None:
                continue

            publish_trip_update(
                result["trip_id"],
                "SIMULATION_TICK",
                notices=
                    simulation_notices(
                        result
                    ),
            )

            if (
                result.get(
                    "trip_status"
                )
                == "COMPLETED"
            ):
                from app.dispatch.collision import (
                    mark_active_searches_collision_dirty,
                )

                mark_active_searches_collision_dirty(
                    (
                        "DRIVER_AVAILABLE_AFTER_TRIP:"
                        f"{result.get('driver_id')}"
                    )
                )

        except Exception as exc:
            db.session.rollback()

            broker_log(
                "SIMULATION TICK FAILED "
                f"job={job_id} "
                f"error={exc}"
            )


def main():
    if not acquire_single_broker_lock():
        print(
            "[BROKER] another broker process already holds "
            f"{BROKER_LOCK_PATH}; exiting",
            flush=True,
        )
        return

    app = create_app(
        start_broker=False
    )

    broker_log(
        f"started build={BROKER_BUILD} "
        f"pid={os.getpid()}"
    )

    broker_log(
        f"simulation_tick="
        f"{SIMULATION_TICK_SECONDS:.3f}s "
        f"collision_tick="
        f"{COLLISION_TICK_SECONDS:.3f}s"
    )

    next_simulation_tick = (
        time.monotonic()
    )

    next_collision_tick = (
        time.monotonic()
    )

    while True:
        now = time.monotonic()

        if now >= next_collision_tick:
            with app.app_context():
                try:
                    run_collision_lane()
                finally:
                    db.session.remove()

            next_collision_tick = (
                now
                + COLLISION_TICK_SECONDS
            )

        if (
            app.config.get(
                "DEMO_MODE"
            )
            and now
            >= next_simulation_tick
        ):
            with app.app_context():
                try:
                    run_simulation_lane()
                finally:
                    db.session.remove()

            next_simulation_tick = (
                now
                + SIMULATION_TICK_SECONDS
            )

        time.sleep(
            IDLE_SLEEP_SECONDS
        )


if __name__ == "__main__":
    main()
