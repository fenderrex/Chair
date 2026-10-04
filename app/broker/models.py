from datetime import datetime, timezone
from app.extensions import db

def utcnow():
    return datetime.now(timezone.utc)

class SimulationJob(db.Model):
    __tablename__ = "simulation_jobs"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, unique=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="READY", index=True)
    phase = db.Column(db.String(30), nullable=False, default="TO_PICKUP", index=True)
    route_geometry_json = db.Column(db.Text, nullable=False)
    route_points_json = db.Column(db.Text, nullable=False)
    current_index = db.Column(db.Integer, nullable=False, default=0)
    progress_percent = db.Column(db.Float, nullable=False, default=0.0)
    step_interval_seconds = db.Column(db.Float, nullable=False, default=0.75)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    paused_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_due_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

