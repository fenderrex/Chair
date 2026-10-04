import json
from datetime import timedelta

from app.extensions import db
from app.location.models import LocationUpdate
from app.maps.services import get_driving_route
from app.trips.models import Trip
from app.drivers.models import Driver

from .models import SimulationJob
from .services import utcnow


def route_points(
    route_geometry,
    min_points=80,
    max_points=140,
):
    """
    DEMO MOTION ONLY.

    Turn route geometry into a dense list of fake GPS points. Production does
    not need this function because real GPS replaces simulated movement.
    """
    coordinates = route_geometry.get(
        "coordinates",
        [],
    )

    if len(coordinates) < 2:
        return []

    segments = []
    total_length = 0.0

    for index in range(
        len(coordinates) - 1
    ):
        lng1, lat1 = coordinates[index]
        lng2, lat2 = coordinates[index + 1]

        dx = float(lng2) - float(lng1)
        dy = float(lat2) - float(lat1)

        length = (
            dx * dx + dy * dy
        ) ** 0.5

        segments.append(
            (
                float(lng1),
                float(lat1),
                float(lng2),
                float(lat2),
                length,
            )
        )

        total_length += length

    target_count = max(
        min_points,
        min(
            max_points,
            len(coordinates),
        ),
    )

    if total_length <= 0:
        lng, lat = coordinates[0]

        return [{
            "latitude": float(lat),
            "longitude": float(lng),
        }]

    points = []

    for point_index in range(
        target_count
    ):
        fraction = (
            point_index
            / max(
                1,
                target_count - 1,
            )
        )

        target_distance = (
            total_length
            * fraction
        )

        walked = 0.0
        selected = segments[-1]

        for segment in segments:
            if (
                walked + segment[4]
                >= target_distance
            ):
                selected = segment
                break

            walked += segment[4]

        (
            lng1,
            lat1,
            lng2,
            lat2,
            segment_length,
        ) = selected

        if segment_length <= 0:
            local_fraction = 0.0
        else:
            local_fraction = (
                target_distance
                - walked
            ) / segment_length

        local_fraction = max(
            0.0,
            min(
                1.0,
                local_fraction,
            ),
        )

        lng = (
            lng1
            + (
                lng2 - lng1
            )
            * local_fraction
        )

        lat = (
            lat1
            + (
                lat2 - lat1
            )
            * local_fraction
        )

        points.append({
            "latitude": lat,
            "longitude": lng,
        })

    return points


def prepare_pickup_motion(
    trip,
    driver,
    job=None,
):
    """
    DEMO MOTION ONLY.

    Build/reset the fake driver -> pickup movement path.
    Validation must already have happened in broker/services.py.
    """
    route = get_driving_route(
        driver.current_latitude,
        driver.current_longitude,
        trip.pickup_latitude,
        trip.pickup_longitude,
    )

    points = route_points(
        route["geometry"]
    )

    if not points:
        raise ValueError(
            "Pickup route has no simulation points"
        )

    if job is None:
        job = SimulationJob(
            trip_id=trip.id,
            driver_id=driver.id,
            phase="TO_PICKUP",
            route_geometry_json=json.dumps(
                route["geometry"]
            ),
            route_points_json=json.dumps(
                points
            ),
        )
        db.session.add(job)
    else:
        job.driver_id = driver.id
        job.phase = "TO_PICKUP"
        job.route_geometry_json = json.dumps(
            route["geometry"]
        )
        job.route_points_json = json.dumps(
            points
        )
        job.current_index = 0
        job.progress_percent = 0.0
        job.started_at = None
        job.paused_at = None
        job.completed_at = None

    job.status = "READY"
    job.next_due_at = None

    trip.status = "DRIVER_ASSIGNED"
    trip.progress_percent = 0.0
    trip.driver_eta_seconds = int(
        route["duration_seconds"]
    )
    trip.driver_arrived_at = None

    db.session.commit()

    return job, route


def prepare_destination_motion(
    trip,
    driver,
    job=None,
):
    """
    DEMO MOTION ONLY.

    Build/reset the fake pickup -> destination movement path.
    Validation must already have happened in broker/services.py.
    """
    route = get_driving_route(
        driver.current_latitude,
        driver.current_longitude,
        trip.destination_latitude,
        trip.destination_longitude,
    )

    points = route_points(
        route["geometry"]
    )

    if not points:
        raise ValueError(
            "Destination route has no simulation points"
        )

    if job is None:
        job = SimulationJob(
            trip_id=trip.id,
            driver_id=driver.id,
            phase="TO_DESTINATION",
            route_geometry_json=json.dumps(
                route["geometry"]
            ),
            route_points_json=json.dumps(
                points
            ),
        )
        db.session.add(job)
    else:
        job.driver_id = driver.id
        job.phase = "TO_DESTINATION"
        job.route_geometry_json = json.dumps(
            route["geometry"]
        )
        job.route_points_json = json.dumps(
            points
        )
        job.current_index = 0
        job.progress_percent = 0.0
        job.started_at = None
        job.paused_at = None
        job.completed_at = None

    job.status = "READY"
    job.next_due_at = None

    trip.progress_percent = 0.0
    trip.driver_eta_seconds = int(
        route["duration_seconds"]
    )

    trip.passenger_current_latitude = (
        driver.current_latitude
    )
    trip.passenger_current_longitude = (
        driver.current_longitude
    )

    db.session.commit()

    return job, route


def advance_demo_job_by_id(
    job_id,
):
    """
    DEMO MOTION ONLY.

    Advance one fake-GPS step. No business validation lives here; start/phase
    permission is handled by normal broker services before a job can RUN.
    """
    job = (
        SimulationJob.query
        .filter_by(id=job_id)
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

    # Absolute race guard: once the passenger has confirmed pickup, the old
    # TO_PICKUP job is forbidden from writing driver position/status again.
    if (
        job.phase == "TO_PICKUP"
        and trip.pickup_confirmed_at
        is not None
    ):
        job.status = "COMPLETED"
        job.next_due_at = None

        if trip.status != "IN_PROGRESS":
            trip.status = "IN_PROGRESS"

        db.session.commit()

        print(
            "[DEMO PICKUP WRITE BLOCKED AFTER CONFIRMATION] "
            f"trip={trip.id} "
            f"job={job.id}",
            flush=True,
        )

        return trip.id

    points = json.loads(
        job.route_points_json
    )

    if not points:
        job.status = "ERROR"
        db.session.commit()
        return False

    if job.current_index >= len(points):
        complete_demo_job(
            job,
            trip,
            driver,
            points[-1],
        )
        db.session.commit()
        return trip.id

    point = points[
        job.current_index
    ]

    now = utcnow()

    driver.current_latitude = (
        point["latitude"]
    )
    driver.current_longitude = (
        point["longitude"]
    )
    driver.last_location_at = now

    db.session.add(
        LocationUpdate(
            trip_id=trip.id,
            actor_type="driver",
            latitude=
                point["latitude"],
            longitude=
                point["longitude"],
            speed=11.5,
            recorded_at=now,
            received_at=now,
        )
    )

    if job.phase == "TO_DESTINATION":
        trip.passenger_current_latitude = (
            point["latitude"]
        )
        trip.passenger_current_longitude = (
            point["longitude"]
        )

        db.session.add(
            LocationUpdate(
                trip_id=trip.id,
                actor_type="passenger",
                latitude=
                    point["latitude"],
                longitude=
                    point["longitude"],
                speed=11.5,
                recorded_at=now,
                received_at=now,
            )
        )

        trip.status = "IN_PROGRESS"

    else:
        trip.status = "DRIVER_EN_ROUTE"

    job.current_index += 1

    total = max(
        1,
        len(points),
    )

    job.progress_percent = min(
        100.0,
        (
            job.current_index
            / total
        )
        * 100.0,
    )

    trip.progress_percent = (
        job.progress_percent
    )

    remaining = max(
        0,
        total - job.current_index,
    )

    trip.driver_eta_seconds = int(
        remaining
        * job.step_interval_seconds
    )

    if (
        job.current_index
        >= len(points)
    ):
        complete_demo_job(
            job,
            trip,
            driver,
            point,
        )

    if job.status == "RUNNING":
        job.next_due_at = (
            now
            + timedelta(
                seconds=float(
                    job.step_interval_seconds
                )
            )
        )
    else:
        job.next_due_at = None

    db.session.commit()

    print(
        "[DEMO MOTION STEP] "
        f"job={job.id} "
        f"trip={trip.id} "
        f"driver={driver.id} "
        f"phase={job.phase} "
        f"index={job.current_index}/{total} "
        f"progress={job.progress_percent:.1f}% "
        f"lat={driver.current_latitude:.6f} "
        f"lng={driver.current_longitude:.6f} "
        f"eta={trip.driver_eta_seconds}s "
        f"status={trip.status}",
        flush=True,
    )

    return trip.id


def complete_demo_job(
    job,
    trip,
    driver,
    point,
):
    """
    DEMO MOTION ONLY.

    Finish the current fake movement phase after the validated state machine
    has allowed that phase to run.
    """
    now = utcnow()

    driver.current_latitude = (
        point["latitude"]
    )
    driver.current_longitude = (
        point["longitude"]
    )
    driver.last_location_at = now

    job.status = "COMPLETED"
    job.progress_percent = 100.0
    job.completed_at = now
    job.next_due_at = None

    trip.progress_percent = 100.0
    trip.driver_eta_seconds = 0

    if job.phase == "TO_PICKUP":
        # Reaching the end of the simulated route does not declare arrival.
        # The driver must explicitly press Arrived at Pickup. That action is
        # what records driver_arrived_at and starts the passenger wait clock.
        trip.status = "DRIVER_EN_ROUTE"
        trip.driver_arrived_at = None

        print(
            "[DEMO MOTION REACHED PICKUP] "
            f"job={job.id} "
            f"trip={trip.id} "
            f"driver={driver.id} "
            "waiting_for_driver_arrival_confirmation=true",
            flush=True,
        )

        return

    trip.passenger_current_latitude = (
        point["latitude"]
    )
    trip.passenger_current_longitude = (
        point["longitude"]
    )

    trip.status = "COMPLETED"
    trip.completed_at = now
    trip.final_fare = (
        trip.estimated_fare
    )

    driver.is_available = True

    print(
        "[DEMO MOTION TRIP COMPLETED] "
        f"job={job.id} "
        f"trip={trip.id} "
        f"driver={driver.id}",
        flush=True,
    )
