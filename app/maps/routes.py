from flask import Blueprint, jsonify, request
from .services import get_route_estimate

bp = Blueprint("maps", __name__)


@bp.post("/estimate")
def estimate():
    data = request.get_json(force=True)
    route = get_route_estimate(
        float(data["pickup_lat"]),
        float(data["pickup_lng"]),
        float(data["destination_lat"]),
        float(data["destination_lng"]),
    )
    return jsonify(route)
