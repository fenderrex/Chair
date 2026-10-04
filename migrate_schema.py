from app import create_app
from app.schema import ensure_schema_updates

app = create_app()

with app.app_context():
    ensure_schema_updates()
    print("Schema is up to date.")
