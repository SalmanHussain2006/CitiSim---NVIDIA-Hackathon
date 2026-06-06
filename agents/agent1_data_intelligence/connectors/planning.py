from datetime import datetime, timezone


def pull_planning_data():
    now = datetime.now(timezone.utc).isoformat()

    return [
        {
            "location": "Liverpool Street",
            "timestamp": now,
            "project_type": "office_development",
            "impact": "high",
            "description": "Large office development expected to increase weekday footfall.",
        },
        {
            "location": "Farringdon",
            "timestamp": now,
            "project_type": "public_realm_upgrade",
            "impact": "medium",
            "description": "Street environment works may temporarily affect pedestrian routes.",
        },
    ]