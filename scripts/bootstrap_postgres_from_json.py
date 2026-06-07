from backend.main import seed_postgres_from_latest_json
from storage import init_db, recent_events_full


def main():
    conn = init_db()
    try:
        before = len(recent_events_full(conn, limit=1000))
        rows = seed_postgres_from_latest_json(conn, limit=1000)
        after = len(recent_events_full(conn, limit=1000))
    finally:
        conn.close()

    print(f"Postgres events before: {before}")
    print(f"Postgres events after: {after}")
    print(f"Seeded from latest Agent 1 JSON: {len(rows)} rows visible")


if __name__ == "__main__":
    main()
