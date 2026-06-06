from datetime import datetime, timezone


def pull_city_events():
    now = datetime.now(timezone.utc).isoformat()

    return [
        {
            "name": "Major City Event",
            "location": "Bank",
            "timestamp": now,
            "expected_attendance": 8000,
            "category": "public_event",
        },
        {
            "name": "Station Area Crowd Pressure",
            "location": "Liverpool Street",
            "timestamp": now,
            "expected_attendance": 5000,
            "category": "transport_related",
        },
    ]