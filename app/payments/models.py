from datetime import datetime, timezone
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False)
    provider = db.Column(db.String(40), nullable=False, default="demo")
    provider_payment_id = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(8), nullable=False, default="USD")

    subtotal = db.Column(db.Float, nullable=False, default=0)
    booking_fee = db.Column(db.Float, nullable=False, default=0)
    distance_charge = db.Column(db.Float, nullable=False, default=0)
    time_charge = db.Column(db.Float, nullable=False, default=0)
    toll_amount = db.Column(db.Float, nullable=False, default=0)
    tip_amount = db.Column(db.Float, nullable=False, default=0)
    tax_amount = db.Column(db.Float, nullable=False, default=0)
    discount_amount = db.Column(db.Float, nullable=False, default=0)

    total_amount = db.Column(db.Float, nullable=False, default=0)
    driver_earnings = db.Column(db.Float, nullable=False, default=0)
    platform_fee = db.Column(db.Float, nullable=False, default=0)

    status = db.Column(db.String(40), nullable=False, default="PENDING")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
