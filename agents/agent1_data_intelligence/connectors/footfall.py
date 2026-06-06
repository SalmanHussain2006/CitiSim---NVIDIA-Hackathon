from datetime import datetime, timezone


def pull_footfall():
    now = datetime.now(timezone.utc).isoformat()

    return [
        {
            "location": "Liverpool Street",
            "timestamp": now,
            "footfall_count": 18500,
            "baseline": 14000,
        },
        {
            "location": "Farringdon",
            "timestamp": now,
            "footfall_count": 10200,
            "baseline": 9500,
        },
        {
            "location": "Bank",
            "timestamp": now,
            "footfall_count": 16000,
            "baseline": 12500,
        },
    ]