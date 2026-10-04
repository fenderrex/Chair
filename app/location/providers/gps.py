from app.location.pipeline import ingest_driver_location


def submit_gps_driver_location(
    driver_id,
    latitude,
    longitude,
):
    return ingest_driver_location(
        driver_id,
        latitude,
        longitude,
        source="gps",
    )
