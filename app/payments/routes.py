from flask import Blueprint, jsonify
from .services import payment_summary

bp = Blueprint("payments", __name__)


@bp.get("/status")
def status():
    return jsonify(payment_summary())
