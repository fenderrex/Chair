from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    with db.engine.connect() as connection:
        result = connection.exec_driver_sql("SELECT DATABASE(), CURRENT_USER()")
        row = result.fetchone()

        print("MYSQL CONNECTION OK")
        print("Database:", row[0])
        print("User:", row[1])
