import json

from app.extensions import db, socketio
from .models import Trip, TripNotice


def serialize_notice(item):
    payload = {}

    if item.payload_json:
        try:
            payload = json.loads(
                item.payload_json
            )
        except Exception:
            payload = {}

    return {
        "id": item.id,
        "trip_id": item.trip_id,
        "sequence": item.sequence,
        "kind": item.kind,
        "message": item.message,
        "payload": payload,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at
            else None
        ),
    }


def record_passenger_notice(
    trip_id,
    kind,
    message,
    *,
    payload=None,
    emit=True,
):
    """
    Persist and optionally emit one passenger-facing broker/lifecycle step.

    This is intentionally separate from trip state. A notice cannot mutate
    dispatch membership, lifecycle status, or simulation position.
    """
    trip = (
        Trip.query
        .filter_by(id=int(trip_id))
        .with_for_update()
        .first()
    )

    if trip is None:
        return None

    trip.notice_sequence = int(
        trip.notice_sequence or 0
    ) + 1

    item = TripNotice(
        trip_id=trip.id,
        sequence=trip.notice_sequence,
        kind=str(kind),
        message=str(message),
        payload_json=(
            json.dumps(
                payload or {}
            )
            if payload
            else None
        ),
    )

    db.session.add(item)
    db.session.commit()

    data = serialize_notice(item)

    if emit:
        socketio.emit(
            "passenger_step",
            data,
            room=f"trip:{trip.id}",
        )

    return data


def recent_trip_notices(
    trip_id,
    limit=20,
):
    items = (
        TripNotice.query
        .filter_by(
            trip_id=int(trip_id)
        )
        .order_by(
            TripNotice.sequence.desc()
        )
        .limit(
            max(1, int(limit))
        )
        .all()
    )

    items.reverse()

    return [
        serialize_notice(item)
        for item in items
    ]
