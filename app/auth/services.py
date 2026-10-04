from werkzeug.security import generate_password_hash

from app.extensions import db
from app.users.models import User
from app.drivers.services import ensure_driver_profile_for_user


ALLOWED_ROLES = {"PASSENGER", "DRIVER"}


def create_account(email, display_name, password, role):
    email = email.strip().lower()
    display_name = display_name.strip()
    role = role.strip().upper()

    if role not in ALLOWED_ROLES:
        raise ValueError("Role must be PASSENGER or DRIVER")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    existing = User.query.filter_by(email=email).first()
    if existing:
        raise ValueError("An account with that email already exists")

    user = User(
        email=email,
        display_name=display_name,
        role=role,
        status="ACTIVE",
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.flush()

    if role == "DRIVER":
        ensure_driver_profile_for_user(user)

    db.session.commit()

    return user
