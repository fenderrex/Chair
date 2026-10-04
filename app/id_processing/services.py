from werkzeug.utils import secure_filename


ALLOWED_DOCUMENT_TYPES = {
    "drivers_license",
    "vehicle_registration",
    "insurance",
    "vehicle_inspection",
}


def prepare_document_for_processing(filename, document_type):
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError("Unsupported document type")

    safe_name = secure_filename(filename)
    return {
        "safe_filename": safe_name,
        "document_type": document_type,
        "processing_status": "QUEUED",
        "pipeline": [
            "malware_scan",
            "image_normalization",
            "barcode_or_mrz_detection",
            "ocr",
            "field_validation",
            "human_review_if_needed",
        ],
    }


def demo_process_identity_document(filename, document_type):
    prepared = prepare_document_for_processing(filename, document_type)

    return {
        **prepared,
        "processing_status": "DEMO_COMPLETE",
        "verification_status": "DEMO_ONLY",
        "extracted": {
            "full_name": "Alex Demo",
            "document_number": "DEMO-REDACTED",
            "issuing_region": "CA",
            "expiration_date": "2030-01-01",
        },
        "warning": (
            "Demo processor only. Do not use this result for real identity verification."
        ),
    }
