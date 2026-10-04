from app.extensions import db
from .models import User


DEMO_USERS = (
    {
        "email": "passenger@example.local",
        "display_name": "Demo Passenger",
        "role": "PASSENGER",
    },
    {
        "email": "admin@example.local",
        "display_name": "Demo Admin",
        "role": "ADMIN",
    },
)


def ensure_demo_users():
    created = []

    for payload in DEMO_USERS:
        user = User.query.filter_by(email=payload["email"]).first()
        if user is None:
            user = User(**payload)
            db.session.add(user)
            created.append(user)

    if created:
        db.session.commit()

    return created


def list_users():
    return User.query.order_by(User.created_at.desc()).all()
