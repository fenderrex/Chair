"""Explicitly create missing sample drivers: python3 seed_demo_drivers.py."""
from app import create_app
from app.drivers.services import ensure_test_drivers
app = create_app(start_broker=False)
with app.app_context():
    print("Created/updated demo drivers:", [d.id for d in ensure_test_drivers()])
