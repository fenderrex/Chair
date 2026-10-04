from flask import Blueprint, jsonify, request

from app.extensions import db
from app.trips.models import Trip
from .models import RideSurvey

bp = Blueprint("surveys", __name__)


def serialize_survey(item):
    return {
        "id": item.id,
        "trip_id": item.trip_id,
        "role": item.role,
        "actor_id": item.actor_id,
        "rating": item.rating,
        "comments": item.comments,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at
            else None
        ),
    }


@bp.post("/trips/<int:trip_id>")
def submit_survey(trip_id):
    trip = db.session.get(
        Trip,
        trip_id,
    )

    if trip is None:
        return jsonify({
            "error": "Trip not found",
        }), 404

    if trip.status != "COMPLETED":
        return jsonify({
            "error":
                "Survey is available after the ride is completed",
        }), 409

    data = request.get_json(
        silent=True,
    ) or {}

    role = str(
        data.get(
            "role",
            "",
        )
    ).upper()

    if role not in {
        "PASSENGER",
        "DRIVER",
    }:
        return jsonify({
            "error":
                "role must be PASSENGER or DRIVER",
        }), 400

    actor_id = data.get(
        "actor_id"
    )

    if actor_id is not None:
        actor_id = int(
            actor_id
        )

    if (
        role == "PASSENGER"
        and trip.passenger_id
        is not None
        and actor_id
        != int(trip.passenger_id)
    ):
        return jsonify({
            "error":
                "Passenger does not own this trip",
        }), 403

    if (
        role == "DRIVER"
        and trip.driver_id
        is not None
        and actor_id
        != int(trip.driver_id)
    ):
        return jsonify({
            "error":
                "Driver does not own this trip",
        }), 403

    try:
        rating = int(
            data["rating"]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return jsonify({
            "error":
                "rating must be an integer from 1 to 5",
        }), 400

    if rating < 1 or rating > 5:
        return jsonify({
            "error":
                "rating must be from 1 to 5",
        }), 400

    item = (
        RideSurvey.query
        .filter_by(
            trip_id=trip.id,
            role=role,
            actor_id=actor_id,
        )
        .first()
    )

    if item is None:
        item = RideSurvey(
            trip_id=trip.id,
            role=role,
            actor_id=actor_id,
            rating=rating,
            comments=str(
                data.get(
                    "comments",
                    "",
                )
            ).strip() or None,
        )
        db.session.add(item)
    else:
        item.rating = rating
        item.comments = str(
            data.get(
                "comments",
                "",
            )
        ).strip() or None

    db.session.commit()

    from app.trips.stream import (
        publish_trip_snapshot,
    )

    publish_trip_snapshot(
        trip.id,
        reason=f"{role}_SURVEY_SUBMITTED",
    )

    return jsonify({
        "ok": True,
        "survey":
            serialize_survey(
                item
            ),
    })


@bp.get("/trips/<int:trip_id>")
def trip_surveys(trip_id):
    items = (
        RideSurvey.query
        .filter_by(
            trip_id=trip_id
        )
        .order_by(
            RideSurvey.id.asc()
        )
        .all()
    )

    return jsonify({
        "trip_id": trip_id,
        "surveys": [
            serialize_survey(item)
            for item in items
        ],
    })
