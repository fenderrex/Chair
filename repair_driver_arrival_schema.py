from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def main():
    app = create_app(start_broker=False)

    with app.app_context():
        inspector = inspect(db.engine)

        if "trips" in inspector.get_table_names():
            trip_columns = {
                column["name"]
                for column in inspector.get_columns("trips")
            }

            if "driver_arrived_at" not in trip_columns:
                db.session.execute(
                    text(
                        "ALTER TABLE `trips` "
                        "ADD COLUMN `driver_arrived_at` DATETIME NULL"
                    )
                )

        # Do not add driver_arrived_at to ride_offers.
        # If an old accidental column exists there, leaving it is harmless,
        # but the ORM no longer references it.

        db.session.commit()

    print("Schema repaired: trips.driver_arrived_at is available.")


if __name__ == "__main__":
    main()
