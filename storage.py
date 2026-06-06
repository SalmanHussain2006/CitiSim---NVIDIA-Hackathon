"""
storage.py - PostgreSQL event store for CityPulse.

This is the shared event layer between Agent 1 and Agent 2.

Agent 1/adapters produce normalised Event records.
Agent 2 reads those same records and builds relationship graphs.

The schema matches Agent 2's expected input:
event_id, event_type, location_id, start_time, impact_score,
duration_minutes, confidence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://urban:urban@localhost:5432/urban_pulse",
)


@dataclass
class Event:
    """
    One normalised city event.

    This shape is intentionally aligned with Agent 2's relationship graph input.
    """

    event_id: str
    event_type: str
    location_id: str
    start_time: datetime
    impact_score: float
    duration_minutes: int
    confidence: float

    source: str = "unknown"
    description: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw: Any = None


def init_db(dsn: str = DATABASE_URL) -> psycopg.Connection:
    """
    Connect to Postgres and create the events table if needed.
    """

    conn = psycopg.connect(dsn, row_factory=dict_row)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            location_id TEXT NOT NULL,
            start_time TIMESTAMPTZ NOT NULL,
            impact_score DOUBLE PRECISION NOT NULL,
            duration_minutes INTEGER NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,

            source TEXT NOT NULL DEFAULT 'unknown',
            description TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            raw_json JSONB,
            ingested_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_type_time
        ON events(event_type, start_time)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_location_time
        ON events(location_id, start_time)
        """
    )

    conn.commit()
    return conn


def upsert_event(conn: psycopg.Connection, event: Event) -> None:
    """
    Insert an event, or update it if the same event_id already exists.

    This prevents duplicates when adapters repeatedly fetch the same incident.
    """

    conn.execute(
        """
        INSERT INTO events (
            event_id,
            event_type,
            location_id,
            start_time,
            impact_score,
            duration_minutes,
            confidence,
            source,
            description,
            latitude,
            longitude,
            raw_json,
            ingested_at
        )
        VALUES (
            %(event_id)s,
            %(event_type)s,
            %(location_id)s,
            %(start_time)s,
            %(impact_score)s,
            %(duration_minutes)s,
            %(confidence)s,
            %(source)s,
            %(description)s,
            %(latitude)s,
            %(longitude)s,
            %(raw_json)s,
            %(ingested_at)s
        )
        ON CONFLICT (event_id) DO UPDATE SET
            event_type = EXCLUDED.event_type,
            location_id = EXCLUDED.location_id,
            start_time = EXCLUDED.start_time,
            impact_score = EXCLUDED.impact_score,
            duration_minutes = EXCLUDED.duration_minutes,
            confidence = EXCLUDED.confidence,
            source = EXCLUDED.source,
            description = EXCLUDED.description,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            raw_json = EXCLUDED.raw_json,
            ingested_at = EXCLUDED.ingested_at
        """,
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "location_id": event.location_id,
            "start_time": event.start_time,
            "impact_score": event.impact_score,
            "duration_minutes": event.duration_minutes,
            "confidence": event.confidence,
            "source": event.source,
            "description": event.description,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "raw_json": Jsonb(event.raw) if event.raw is not None else None,
            "ingested_at": datetime.now(timezone.utc),
        },
    )

    conn.commit()


def recent_events(
    conn: psycopg.Connection,
    event_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Read recent events back out.

    These records can be passed directly into Agent 2's run_agent2().
    """

    if event_type:
        cur = conn.execute(
            """
            SELECT
                event_id,
                event_type,
                location_id,
                start_time,
                impact_score,
                duration_minutes,
                confidence
            FROM events
            WHERE event_type = %s
            ORDER BY ingested_at DESC
            LIMIT %s
            """,
            (event_type, limit),
        )
    else:
        cur = conn.execute(
            """
            SELECT
                event_id,
                event_type,
                location_id,
                start_time,
                impact_score,
                duration_minutes,
                confidence
            FROM events
            ORDER BY ingested_at DESC
            LIMIT %s
            """,
            (limit,),
        )

    return cur.fetchall()


def recent_events_full(conn: psycopg.Connection, limit: int = 50) -> list[dict]:
    """
    Full version including metadata/raw payload.
    Useful for debugging, frontend, or recommendations.
    """

    cur = conn.execute(
        """
        SELECT *
        FROM events
        ORDER BY ingested_at DESC
        LIMIT %s
        """,
        (limit,),
    )

    return cur.fetchall()


if __name__ == "__main__":
    conn = init_db()

    demo = Event(
        event_id="demo-roadworks-001",
        event_type="roadworks",
        location_id="camden_high_street",
        start_time=datetime.now(timezone.utc),
        impact_score=0.82,
        duration_minutes=180,
        confidence=0.88,
        source="demo",
        description="Demo roadworks on Camden High Street",
        raw={"example": True},
    )

    upsert_event(conn, demo)
    upsert_event(conn, demo)

    rows = recent_events(conn)

    print(f"rows in events: {len(rows)} (should be 1, not 2)")
    print("stored event:", rows[0])