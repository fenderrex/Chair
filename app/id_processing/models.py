from datetime import datetime, timezone
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class IdentityDocument(db.Model):
    __tablename__ = "identity_documents"

    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)

    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(512), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)

    processing_status = db.Column(db.String(40), nullable=False, default="PENDING")
    verification_status = db.Column(db.String(40), nullable=False, default="UNREVIEWED")
    extracted_json = db.Column(db.Text, nullable=True)

    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
