from datetime import timezone, datetime


def iso_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def trip_timing(trip):
    from .models import TripStageEvent
    events = TripStageEvent.query.filter_by(trip_id=trip.id).order_by(TripStageEvent.entered_at, TripStageEvent.id).all()
    # Older trips have no history: use known DB timestamps, never invented times.
    history = [{"status": e.status, "entered_at": iso_utc(e.entered_at)} for e in events]
    known = [("REQUESTED", trip.requested_at), ("DRIVER_ASSIGNED", trip.accepted_at),
             ("DRIVER_ARRIVED", trip.driver_arrived_at), ("PICKUP_PENDING", trip.pickup_claimed_at),
             ("IN_PROGRESS", trip.started_at), ("COMPLETED", trip.completed_at), ("CANCELED", trip.canceled_at)]
    cutoff = history[0]["entered_at"] if history else None
    history = [{"status": s, "entered_at": iso_utc(t)} for s, t in known
               if t and (cutoff is None or iso_utc(t) < cutoff)] + history
    return {"server_time": iso_utc(datetime.now(timezone.utc)), "stages": history}
