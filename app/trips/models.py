from datetime import datetime, timezone
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Trip(db.Model):
    __tablename__ = "trips"

    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    passenger_name = db.Column(db.String(120), nullable=False, default="Demo Passenger")

    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=True)
    offered_driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=True)
    offered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    offer_rank = db.Column(db.Integer, nullable=True)

    dispatch_started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_dispatch_at = db.Column(db.DateTime(timezone=True), nullable=True)
    dispatch_wave = db.Column(db.Integer, nullable=False, default=0)

    # Collision/match scheduler state. This lane is separate from simulation.
    collision_dirty = db.Column(db.Boolean, nullable=False, default=False, index=True)
    collision_reason = db.Column(db.String(80), nullable=True)
    collision_requested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    collision_revision = db.Column(db.Integer, nullable=False, default=0)

    # Monotonic passenger-facing broker notice sequence.
    notice_sequence = db.Column(db.Integer, nullable=False, default=0)

    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="REQUESTED")

    pickup_latitude = db.Column(db.Float, nullable=False)
    pickup_longitude = db.Column(db.Float, nullable=False)
    passenger_current_latitude = db.Column(db.Float, nullable=True)
    passenger_current_longitude = db.Column(db.Float, nullable=True)
    destination_latitude = db.Column(db.Float, nullable=False)
    destination_longitude = db.Column(db.Float, nullable=False)

    estimated_distance_meters = db.Column(db.Float, nullable=False)
    estimated_duration_seconds = db.Column(db.Float, nullable=False)
    estimated_fare = db.Column(db.Float, nullable=False)
    original_estimated_fare = db.Column(db.Float, nullable=True)
    fare_multiplier = db.Column(db.Float, nullable=False, default=1.25)
    fare_round = db.Column(db.Integer, nullable=False, default=0)
    fare_wait_until = db.Column(db.DateTime(timezone=True), nullable=True)
    fare_review_pending = db.Column(db.Boolean, nullable=False, default=False)
    no_driver_admin_notified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    final_fare = db.Column(db.Float, nullable=True)

    progress_percent = db.Column(db.Float, nullable=False, default=0.0)
    driver_eta_seconds = db.Column(db.Integer, nullable=True)

    route_provider = db.Column(db.String(40), nullable=False)
    route_geometry_json = db.Column(db.Text, nullable=False)

    requested_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    driver_arrived_at = db.Column(db.DateTime(timezone=True), nullable=True)
    pickup_claimed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    pickup_confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    pickup_help_requested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cancel_locked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    canceled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class RideOffer(db.Model):
    __tablename__ = "ride_offers"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trips.id"),
        nullable=False,
        index=True,
    )
    driver_id = db.Column(
        db.Integer,
        db.ForeignKey("drivers.id"),
        nullable=False,
        index=True,
    )

    rank = db.Column(db.Integer, nullable=False)
    distance_miles = db.Column(db.Float, nullable=False)
    pickup_eta_seconds = db.Column(db.Integer, nullable=False)
    distance_fraction = db.Column(db.Float, nullable=True)
    response_seconds = db.Column(db.Integer, nullable=True)
    dispatch_score = db.Column(db.Float, nullable=False)
    eligible_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)

    status = db.Column(
        db.String(30),
        nullable=False,
        default="OFFERED",
        index=True,
    )

    offered_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    declined_at = db.Column(db.DateTime(timezone=True), nullable=True)
    accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("trip_id", "driver_id", name="uq_ride_offer_trip_driver"),
    )


class FareEscalation(db.Model):
    __tablename__ = "fare_escalations"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trips.id"),
        nullable=False,
        index=True,
    )
    round_number = db.Column(db.Integer, nullable=False)
    original_fare = db.Column(db.Float, nullable=False)
    multiplier = db.Column(db.Float, nullable=False)
    offered_fare = db.Column(db.Float, nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="PENDING",
        index=True,
    )
    prompted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    responded_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "round_number",
            name="uq_fare_escalation_trip_round",
        ),
    )



class TripStageEvent(db.Model):
    __tablename__ = "trip_stage_events"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False)
    entered_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    trip = db.relationship("Trip")


from sqlalchemy import event, inspect
from sqlalchemy.orm import Session


@event.listens_for(Session, "before_flush")
def record_trip_stage(session, flush_context, instances):
    for trip in list(session.new) + list(session.dirty):
        if not isinstance(trip, Trip) or trip in session.deleted:
            continue
        if trip in session.new or inspect(trip).attrs.status.history.has_changes():
            session.add(TripStageEvent(trip=trip, status=trip.status or "REQUESTED", entered_at=utcnow()))



class TripNotice(db.Model):
    __tablename__ = "trip_notices"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trips.id"),
        nullable=False,
        index=True,
    )
    sequence = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(60), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    payload_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "sequence",
            name="uq_trip_notice_trip_sequence",
        ),
    )
