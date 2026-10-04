from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class RideSurvey(db.Model):
    __tablename__ = "ride_surveys"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trips.id"),
        nullable=False,
        index=True,
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    actor_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    rating = db.Column(
        db.Integer,
        nullable=False,
    )

    comments = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "trip_id",
            "role",
            "actor_id",
            name="uq_ride_survey_trip_role_actor",
        ),
    )
