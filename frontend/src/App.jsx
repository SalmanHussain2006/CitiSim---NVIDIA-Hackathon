import { useEffect, useState } from "react";
import "./style.css";

const API = "http://localhost:8000";

function StatCard({ title, value }) {
  return (
    <div className="stat-card">
      <p>{title}</p>
      <h2>{value}</h2>
    </div>
  );
}

function EventList({ events }) {
  return (
    <div className="panel">
      <h2>Live Agent 1 Events</h2>
      {events.slice(0, 10).map((event) => (
        <div className="event-card" key={event.id}>
          <div className="event-top">
            <strong>{event.location}</strong>
            <span className={`severity ${event.severity}`}>
              {event.severity}
            </span>
          </div>
          <p>{event.summary}</p>
          <small>{event.event_type}</small>
        </div>
      ))}
    </div>
  );
}

function RelationshipPanel({ relationships }) {
  const items = relationships?.relationships || [];

  return (
    <div className="panel">
      <h2>Agent 2 Insights</h2>
      {items.length === 0 && <p>No relationships generated yet.</p>}
      {items.slice(0, 6).map((item) => (
        <div className="event-card" key={item.id}>
          <strong>{item.location}</strong>
          <p>{item.finding}</p>
          <small>Confidence: {item.confidence}</small>
        </div>
      ))}
    </div>
  );
}

function ForecastPanel({ forecasts }) {
  const items = forecasts?.forecasts || forecasts?.predictions || [];

  return (
    <div className="panel">
      <h2>Agent 3 Forecasts</h2>
      {items.length === 0 && <p>No forecasts generated yet.</p>}
      {items.slice(0, 6).map((item, index) => (
        <div className="event-card" key={index}>
          <strong>{item.location || "City of London"}</strong>
          <p>{item.summary || item.forecast || JSON.stringify(item)}</p>
        </div>
      ))}
    </div>
  );
}

function RecommendationPanel({ recommendations }) {
  const items =
    recommendations?.recommendations ||
    recommendations?.actions ||
    [];

  return (
    <div className="panel">
      <h2>Agent 4 Recommendations</h2>
      {items.length === 0 && <p>No recommendations generated yet.</p>}
      {items.slice(0, 6).map((item, index) => (
        <div className="event-card recommendation" key={index}>
          <strong>{item.location || "City Operations"}</strong>
          <p>{item.recommendation || item.summary || JSON.stringify(item)}</p>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [events, setEvents] = useState([]);
  const [relationships, setRelationships] = useState({});
  const [forecasts, setForecasts] = useState({});
  const [recommendations, setRecommendations] = useState({});

  async function loadData() {
    const [eventsRes, relRes, forecastRes, recRes] = await Promise.all([
      fetch(`${API}/events`),
      fetch(`${API}/relationships`),
      fetch(`${API}/forecasts`),
      fetch(`${API}/recommendations`),
    ]);

    setEvents(await eventsRes.json());
    setRelationships(await relRes.json());
    setForecasts(await forecastRes.json());
    setRecommendations(await recRes.json());
  }

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  const roadEvents = events.filter((e) => e.event_type === "road_disruption");
  const transportEvents = events.filter((e) =>
    e.event_type?.includes("transport")
  );
  const highSeverity = events.filter((e) => e.severity === "high");

  return (
    <main>
      <header>
        <h1>Urban Pulse</h1>
        <p>Autonomous City Operations Intelligence Platform</p>
      </header>

      <section className="stats">
        <StatCard title="Total Events" value={events.length} />
        <StatCard title="Road Events" value={roadEvents.length} />
        <StatCard title="Transport Events" value={transportEvents.length} />
        <StatCard title="High Severity" value={highSeverity.length} />
      </section>

      <section className="grid">
        <EventList events={events} />
        <RelationshipPanel relationships={relationships} />
        <ForecastPanel forecasts={forecasts} />
        <RecommendationPanel recommendations={recommendations} />
      </section>
    </main>
  );
}