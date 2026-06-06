"""
storage.py - the local store for Urban Pulse (PostgreSQL version).

Same idea as before: every adapter produces normalised Event records and writes
them here; the agents read from here and nowhere else. Now backed by Postgres,
which matches the project plan and gives us JSONB (queryable raw payloads),
proper timestamp types, and room to add PostGIS for geo queries later.

Setup (one-off):
  1. Run a Postgres server. Quickest is Docker:
       docker run --name urban-pg -e POSTGRES_USER=urban \
         -e POSTGRES_PASSWORD=urban -e POSTGRES_DB=urban_pulse \
         -p 5432:5432 -d postgres:16
  2. pip install "psycopg[binary]"
  3. (optional) export DATABASE_URL=postgresql://urban:urban@localhost:5432/urban_pulse

Then prove it works:  python storage.py
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
    """One normalised record. Every adapter produces these, whatever the source."""
    id: str                                # stable, derived from the source's own id (de-duplication key)
    source: str                            # e.g. "tfl_line", "tfl_road", "londonair", "weather"
    category: str                          # e.g. "transport", "roadworks", "incident", "air_quality", "weather"
    description: str = ""                  # human-readable summary
    timestamp: Optional[datetime] = None   # when the event applies
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None    # line, borough, road name...
    value: Optional[float] = None          # numeric measurement or severity score
    raw: Any = None                        # the original payload, kept verbatim (stored as JSONB)


def init_db(dsn: str = DATABASE_URL) -> psycopg.Connection:
    """Connect (and create the table if needed). Returns an open connection."""
    conn = psycopg.connect(dsn, row_factory=dict_row)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id            TEXT PRIMARY KEY,
            source        TEXT NOT NULL,
            category      TEXT NOT NULL,
            description   TEXT,
            timestamp     TIMESTAMPTZ,
            latitude      DOUBLE PRECISION,
            longitude     DOUBLE PRECISION,
            location_name TEXT,
            value         DOUBLE PRECISION,
            raw_json      JSONB,
            ingested_at   TIMESTAMPTZ NOT NULL
        )
        """
    )
    # Helps the agents query "what's recent in this category" quickly.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_cat_time ON events(category, timestamp)")
    conn.commit()
    return conn


def upsert_event(conn: psycopg.Connection, event: Event) -> None:
    """
    Insert a new event, or update it if we've seen its id before.

    The id is the dedup key: when the scheduler re-fetches the same roadworks
    every few minutes, the row is refreshed in place instead of duplicated.
    """
    conn.execute(
        """
        INSERT INTO events (id, source, category, description, timestamp,
                            latitude, longitude, location_name, value, raw_json, ingested_at)
        VALUES (%(id)s, %(source)s, %(category)s, %(description)s, %(timestamp)s,
                %(latitude)s, %(longitude)s, %(location_name)s, %(value)s, %(raw_json)s, %(ingested_at)s)
        ON CONFLICT (id) DO UPDATE SET
            description   = EXCLUDED.description,
            timestamp     = EXCLUDED.timestamp,
            latitude      = EXCLUDED.latitude,
            longitude     = EXCLUDED.longitude,
            location_name = EXCLUDED.location_name,
            value         = EXCLUDED.value,
            raw_json      = EXCLUDED.raw_json,
            ingested_at   = EXCLUDED.ingested_at
        """,
        {
            "id": event.id,
            "source": event.source,
            "category": event.category,
            "description": event.description,
            "timestamp": event.timestamp,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "location_name": event.location_name,
            "value": event.value,
            "raw_json": Jsonb(event.raw) if event.raw is not None else None,
            "ingested_at": datetime.now(timezone.utc),
        },
    )
    conn.commit()


def recent_events(conn: psycopg.Connection, category: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Read events back out - the door the downstream agents use."""
    if category:
        cur = conn.execute(
            "SELECT * FROM events WHERE category = %s ORDER BY ingested_at DESC LIMIT %s",
            (category, limit),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM events ORDER BY ingested_at DESC LIMIT %s",
            (limit,),
        )
    return cur.fetchall()


if __name__ == "__main__":
    # Needs a running Postgres (see Setup at the top). Then: python storage.py
    conn = init_db()
    demo = Event(
        id="demo-1",
        source="tfl_line",
        category="transport",
        description="Central line: minor delays",
        timestamp=datetime.now(timezone.utc),
        location_name="Central line",
        value=9,
        raw={"example": True},
    )
    upsert_event(conn, demo)
    upsert_event(conn, demo)  # second time updates the same row, does NOT duplicate
    rows = recent_events(conn, category="transport")
    print(f"rows in 'transport': {len(rows)}  (should be 1, not 2)")
    print("stored description:", rows[0]["description"])