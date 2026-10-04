from .timing import utcnow


def dispatch_countup(
    started_at,
    total_seconds,
    now=None,
):
    """
    Convert the existing countdown into a count-up value.

    countdown_remaining = total - elapsed
    countup_elapsed = total - countdown_remaining

    The returned elapsed value is intentionally NOT capped at total_seconds.
    That allows the same linear expansion scale to exceed 1.0 later.
    """
    total = max(
        0.001,
        float(total_seconds),
    )

    current = now or utcnow()

    if started_at is None:
        return {
            "total_seconds": total,
            "remaining_seconds": total,
            "elapsed_seconds": 0.0,
            "expansion_fraction": 0.0,
        }

    compare_now = current

    if (
        getattr(started_at, "tzinfo", None)
        is None
        and getattr(compare_now, "tzinfo", None)
        is not None
    ):
        compare_now = compare_now.replace(
            tzinfo=None
        )

    raw_elapsed = max(
        0.0,
        (
            compare_now
            - started_at
        ).total_seconds(),
    )

    # This is the important inversion:
    # remaining counts DOWN, elapsed counts UP.
    remaining = max(
        0.0,
        total - raw_elapsed,
    )

    elapsed = (
        total - remaining
        if raw_elapsed <= total
        else raw_elapsed
    )

    return {
        "total_seconds": total,
        "remaining_seconds": remaining,
        "elapsed_seconds": elapsed,
        "expansion_fraction": (
            elapsed / total
        ),
    }

def current_dispatch_expansion(
    trip,
    settings,
    now=None,
):
    """
    PIPELINE 01 SEARCH CLOCK

    A search begins immediately at the admin-configured initial radius, then
    expands by radius_miles after each expansion interval until max_radius_miles
    is reached. A higher-fare round resets dispatch_started_at, so the same
    clock naturally restarts at the initial radius.

    Example:
        initial_radius_miles = 3
        radius_miles = 2.5
        max_radius_miles = 10.5
        expansion_seconds = 20

        at request time -> 3.0 miles
        at 20 sec        -> 5.5 miles
        at 40 sec        -> 8.0 miles
        at 60 sec        -> 10.5 miles (cap)
    """
    timer_seconds = max(
        0.001,
        float(settings["expansion_seconds"]),
    )

    radius_step = max(
        0.001,
        float(settings["radius_miles"]),
    )

    initial_radius = max(
        0.0,
        float(settings.get("initial_radius_miles", 3.0)),
    )

    max_radius = max(
        initial_radius,
        float(settings.get("max_radius_miles", initial_radius)),
    )

    current = now or utcnow()

    if trip.dispatch_started_at is None:
        elapsed_seconds = 0.0
    else:
        started_at = trip.dispatch_started_at

        if (
            getattr(started_at, "tzinfo", None) is None
            and getattr(current, "tzinfo", None) is not None
        ):
            current = current.replace(tzinfo=None)

        elapsed_seconds = max(
            0.0,
            (current - started_at).total_seconds(),
        )

    completed_intervals = int(
        elapsed_seconds // timer_seconds
    )

    seconds_into_interval = (
        elapsed_seconds
        - completed_intervals * timer_seconds
    )

    raw_search_radius = (
        initial_radius
        + completed_intervals * radius_step
    )
    search_radius = min(
        raw_search_radius,
        max_radius,
    )
    radius_capped = (
        search_radius >= max_radius - 1e-9
    )

    seconds_until_next_increase = (
        0.0
        if radius_capped
        else max(
            0.0,
            timer_seconds - seconds_into_interval,
        )
    )

    return {
        "total_seconds": timer_seconds,
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": seconds_until_next_increase,
        "expansion_fraction": (
            1.0
            if radius_capped
            else seconds_into_interval / timer_seconds
        ),
        "completed_intervals": completed_intervals,
        "initial_radius_miles": initial_radius,
        "radius_step_miles": radius_step,
        "search_radius_miles": search_radius,
        "raw_search_radius_miles": raw_search_radius,
        "max_radius_miles": max_radius,
        "radius_capped": radius_capped,
        "radius_paused": radius_capped,
    }

