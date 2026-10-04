from flask import Blueprint, jsonify

from .services import list_users

bp = Blueprint("users", __name__)


@bp.get("/")
def users_index():
    users = list_users()
    return jsonify([
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at.isoformat(),
        }
        for user in users
    ])
