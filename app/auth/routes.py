from flask import Blueprint, jsonify, render_template, request

from .services import create_account

bp = Blueprint("auth", __name__)


@bp.get("/signup")
def signup_page():
    return render_template("signup.html")


@bp.post("/signup")
def signup_submit():
    data = request.get_json(silent=True) or request.form

    try:
        user = create_account(
            email=data.get("email", ""),
            display_name=data.get("display_name", ""),
            password=data.get("password", ""),
            role=data.get("role", "PASSENGER"),
        )
    except ValueError as exc:
        if request.is_json:
            return jsonify({"ok": False, "error": str(exc)}), 400

        return render_template(
            "signup.html",
            error=str(exc),
            values={
                "email": data.get("email", ""),
                "display_name": data.get("display_name", ""),
                "role": data.get("role", "PASSENGER"),
            },
        ), 400

    from app.admin.platform_map import publish_platform_map
    publish_platform_map()
    if request.is_json:
        return jsonify({
            "ok": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "status": user.status,
            },
        }), 201

    return render_template("signup_success.html", user=user)
