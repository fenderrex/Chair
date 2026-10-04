from dataclasses import dataclass, field

from app.dispatch.collision import (
    mark_active_searches_collision_dirty,
)
from .driver_location import (
    set_driver_location,
)


@dataclass
class LocationIngestResult:
    driver: object
    proximity_events: list = field(
        default_factory=list
    )


def ingest_driver_location(
    driver_id,
    latitude,
    longitude,
    *,
    source,
):
    """
    Shared driver location pipeline.

    1. Commit the driver position.
    2. Mark passenger-search collision checks dirty.
    3. Return immediately.

    No search matching and no simulation stepping happens in this request.
    """
    driver = set_driver_location(
        driver_id,
        latitude,
        longitude,
        source=source,
        emit=True,
    )

    if driver is None:
        return LocationIngestResult(
            driver=None,
            proximity_events=[],
        )

    trip_ids = (
        mark_active_searches_collision_dirty(
            f"DRIVER_POSITION:{int(driver_id)}"
        )
    )

    return LocationIngestResult(
        driver=driver,
        proximity_events=[
            {
                "trip_id":
                    int(trip_id),
                "trigger":
                    "DRIVER_POSITION",
            }
            for trip_id in trip_ids
        ],
    )
