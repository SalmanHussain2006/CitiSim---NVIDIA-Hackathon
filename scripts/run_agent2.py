from storage import init_db, recent_events
from agents.agent2_relationship_discovery.agent2 import run_agent2

conn = init_db()
records = recent_events(conn, limit=100)

graph_payload = run_agent2(records)
print(graph_payload)