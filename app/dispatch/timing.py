from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)

def comparable_now(value=None):
    now = utcnow()
    if value is not None and value.tzinfo is None:
        return now.replace(tzinfo=None)
    return now

def seconds_until(value):
    if value is None:
        return None

    now = comparable_now(value)

    return max(
        0,
        int((value - now).total_seconds()),
    )
