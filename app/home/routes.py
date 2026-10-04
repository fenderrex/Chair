from flask import Blueprint, render_template, request

bp = Blueprint("home", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/passenger")
def passenger_view():
    from app.users.models import User

    user_id = request.args.get("user_id", type=int)
    passenger = None

    if user_id is not None:
        passenger = User.query.filter_by(id=user_id, role="PASSENGER").first()

    if passenger is None:
        passenger = (
            User.query
            .filter_by(role="PASSENGER")
            .order_by(User.id.asc())
            .first()
        )

    return render_template(
        "passenger.html",
        passenger=passenger,
    )


@bp.get("/driver")
def driver_view():
    from flask import request
    driver_id = request.args.get("driver_id", default=1, type=int)
    return render_template("driver.html", driver_id=driver_id)
