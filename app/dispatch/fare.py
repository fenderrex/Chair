BASE_FARE = 2.50
PRICE_PER_MILE = 1.50
PRICE_PER_MINUTE = 0.20
BOOKING_FEE = 2.00
MINIMUM_FARE = 7.00
ASSUMED_PICKUP_SPEED_MPH = 25.0


def calculate_fare_estimate(route):
    distance_component = route["distance_miles"] * PRICE_PER_MILE
    time_component = route["duration_minutes"] * PRICE_PER_MINUTE

    total = max(
        MINIMUM_FARE,
        BASE_FARE
        + distance_component
        + time_component
        + BOOKING_FEE,
    )

    return {
        "base_fare": round(BASE_FARE, 2),
        "distance_charge": round(distance_component, 2),
        "time_charge": round(time_component, 2),
        "booking_fee": round(BOOKING_FEE, 2),
        "estimated_total": round(total, 2),
        "currency": "USD",
    }

def estimate_pickup_eta_seconds(distance_miles):
    seconds = (
        float(distance_miles)
        / ASSUMED_PICKUP_SPEED_MPH
        * 3600.0
    )

    return max(
        45,
        int(round(seconds)),
    )
