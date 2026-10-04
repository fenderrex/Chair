from flask import Blueprint, jsonify, request
from .services import demo_process_identity_document

bp = Blueprint("id_processing", __name__)


@bp.post("/demo")
def demo_process():
    data = request.get_json(force=True)
    result = demo_process_identity_document(
        filename=data.get("filename", "license.jpg"),
        document_type=data.get("document_type", "drivers_license"),
    )
    return jsonify(result)
