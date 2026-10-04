from flask import Blueprint, jsonify, request

from .services import create_message, list_messages, serialize_message

bp = Blueprint("messages", __name__)


@bp.get("/")
def message_index():
    trip_id = request.args.get("trip_id", type=int)
    return jsonify(list_messages(trip_id=trip_id))


@bp.post("/")
def send_message():
    data = request.get_json(force=True)

    required = ("sender_role", "sender_name", "recipient_role", "body")
    missing = [name for name in required if not str(data.get(name, "")).strip()]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    message = create_message(
        sender_role=data["sender_role"],
        sender_name=data["sender_name"],
        recipient_role=data["recipient_role"],
        body=data["body"],
        trip_id=data.get("trip_id"),
    )
    return jsonify(serialize_message(message)), 201
