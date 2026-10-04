from app.extensions import db, socketio
from .models import Message


def create_message(sender_role, sender_name, recipient_role, body, trip_id=None):
    message = Message(
        trip_id=trip_id,
        sender_role=sender_role,
        sender_name=sender_name,
        recipient_role=recipient_role,
        body=body.strip(),
    )
    db.session.add(message)
    db.session.commit()

    payload = serialize_message(message)
    socketio.emit("chat_message", payload)
    return message


def serialize_message(message):
    return {
        "id": message.id,
        "trip_id": message.trip_id,
        "sender_role": message.sender_role,
        "sender_name": message.sender_name,
        "recipient_role": message.recipient_role,
        "body": message.body,
        "is_system": message.is_system,
        "created_at": message.created_at.isoformat(),
    }


def list_messages(trip_id=None, limit=100):
    query = Message.query
    if trip_id is not None:
        query = query.filter_by(trip_id=trip_id)

    rows = query.order_by(Message.created_at.asc()).limit(limit).all()
    return [serialize_message(row) for row in rows]
