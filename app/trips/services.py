"""
Compatibility facade for the trip/dispatch services.

The implementation was split into smaller domain modules so local coding
agents do not need to load one very large file. Existing imports from
`app.trips.services` continue to work.
"""

from app.dispatch.timing import (
    utcnow,
    comparable_now,
    seconds_until,
)
from app.dispatch.radius import (
    dispatch_countup,
    current_dispatch_expansion,
)
from app.dispatch.fare import (
    calculate_fare_estimate,
    estimate_pickup_eta_seconds,
)
from app.dispatch.queue import (
    _driver_offer_for_trip,
    _open_offers,
    _waiting_offers,
    _refresh_trip_dispatch_summary,
)
from app.dispatch.serialization import (
    serialize_trip_request,
)
from app.dispatch.plan import (
    build_dispatch_plan,
)
from app.dispatch.proximity import (
    activate_due_offers,
)
from app.dispatch.worker import (
    process_proximity_service,
)
from app.dispatch.fare_rounds import (
    _maybe_start_last_driver_wait,
    _maybe_open_fare_review,
    process_fare_escalation_watch,
    accept_fare_escalation,
    decline_fare_escalation,
    process_dispatch_queue,
)
from .requests_service import (
    get_active_trip_for_passenger,
    create_trip_request,
    active_requests,
)
from .lifecycle import (
    _close_other_offers,
    accept_trip_offer,
    decline_trip_offer,
    driver_mark_arrived,
    driver_claim_pickup,
    passenger_request_pickup_help,
    passenger_confirm_pickup,
    cancel_trip,
)

__all__ = [
    "utcnow",
    "comparable_now",
    "seconds_until",
    "dispatch_countup",
    "current_dispatch_expansion",
    "calculate_fare_estimate",
    "estimate_pickup_eta_seconds",
    "_driver_offer_for_trip",
    "_open_offers",
    "_waiting_offers",
    "_refresh_trip_dispatch_summary",
    "serialize_trip_request",
    "get_active_trip_for_passenger",
    "create_trip_request",
    "build_dispatch_plan",
    "activate_due_offers",
    "_maybe_start_last_driver_wait",
    "_maybe_open_fare_review",
    "process_fare_escalation_watch",
    "accept_fare_escalation",
    "decline_fare_escalation",
    "process_proximity_service",
    "process_dispatch_queue",
    "_close_other_offers",
    "accept_trip_offer",
    "decline_trip_offer",
    "driver_mark_arrived",
    "driver_claim_pickup",
    "passenger_request_pickup_help",
    "passenger_confirm_pickup",
    "active_requests",
    "cancel_trip",
]
