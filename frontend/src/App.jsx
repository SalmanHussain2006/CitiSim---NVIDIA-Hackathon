import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import "./style.css";

const API = import.meta.env.VITE_API_URL || "";

function normalizeText(value) {
  return String(value || "").toLowerCase();
}

function getEventText(event) {
  return `
    ${event.source_agent || ""}
    ${event.location || ""}
    ${event.location_id || ""}
    ${event.event_type || ""}
    ${event.severity || ""}
    ${event.summary || ""}
    ${event.title || ""}
    ${event.action || ""}
  `.toLowerCase();
}

function formatAgentItem(item) {
  if (item.summary) return item.summary;
  if (item.title && item.action) return `${item.title}: ${item.action}`;
  if (item.title) return item.title;
  if (item.outcome) return `${item.outcome.replaceAll("_", " ")} risk at ${item.location_id}`;
  if (item.node_id) return item.summary || item.node_id;
  if (item.event_type) return `${item.event_type} at ${item.location || item.location_id || "Unknown"}`;
  return JSON.stringify(item);
}

function EventCard({ event }) {
  return (
    <div className="event-card">
      <div className="event-top">
        <div>
          <strong>{event.location || event.location_id || "Unknown location"}</strong>
          <small>{event.event_type || "unknown_event"}</small>
        </div>

        <span className={`severity ${event.severity || "low"}`}>
          {event.severity || "low"}
        </span>
      </div>

      <p>{event.summary || "No summary available."}</p>
    </div>
  );
}

function AgentCard({ agent }) {
  return (
    <article className="agent-card">
      <div className="agent-card-top">
        <div>
          <span className="agent-kicker">{agent.name}</span>
          <h3>{agent.title}</h3>
        </div>
        <span className="agent-status">{agent.status}</span>
      </div>

      <p>{agent.summary}</p>

      <div className="agent-metric">
        <strong>{agent.metric ?? 0}</strong>
        <span>{agent.metric_label}</span>
      </div>

      {agent.items?.length > 0 && (
        <div className="agent-items">
          {agent.items.slice(0, 4).map((item, index) => (
            <div className="agent-item" key={item.id || item.event_id || item.node_id || index}>
              {formatAgentItem(item)}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function RecommendationCard({ recommendation }) {
  if (typeof recommendation === "string") {
    return <div className="rec">{recommendation}</div>;
  }

  return (
    <div className={`rec priority-${recommendation.priority || "medium"}`}>
      <strong>
        {recommendation.title || recommendation.action || "Operational recommendation"}
        {recommendation.generated_by === "nemotron" && (
          <span className="nemotron-tag">Nemotron</span>
        )}
      </strong>
      {recommendation.action && <span>{recommendation.action}</span>}
    </div>
  );
}

export default function App() {
  const [prompt, setPrompt] = useState("");
  const [events, setEvents] = useState([]);
  const [agents, setAgents] = useState([]);
  const [dataSource, setDataSource] = useState(null);
  const [matchedEvents, setMatchedEvents] = useState([]);
  const [simulation, setSimulation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [searchMessage, setSearchMessage] = useState("");
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioChunksRef = useRef([]);

  useEffect(() => {
    let cancelled = false;

    Promise.all([fetch(`${API}/events`), fetch(`${API}/agents`), fetch(`${API}/data-source`)])
      .then(async ([eventsRes, agentsRes, sourceRes]) => {
        const eventsData = await eventsRes.json();
        const agentsData = await agentsRes.json();
        const sourceData = await sourceRes.json();

        if (!cancelled) {
          setEvents(Array.isArray(eventsData) ? eventsData : []);
          setAgents(Array.isArray(agentsData) ? agentsData : []);
          setDataSource(sourceData);
        }
      })
      .catch((error) => {
        console.error("Failed to load agent data:", error);

        if (!cancelled) {
          setEvents([]);
          setAgents([]);
          setDataSource(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const totalEvents = events.length;

  const highSeverityCount = useMemo(
    () => events.filter((event) => event.severity === "high").length,
    [events]
  );

  const activeAgentCount = useMemo(
    () => agents.filter((agent) => agent.status === "active").length,
    [agents]
  );

  function searchPrompt() {
    const query = normalizeText(prompt).trim();

    if (!query) {
      setMatchedEvents([]);
      setSimulation(null);
      setSearchMessage("Enter a prompt before searching.");
      return;
    }

    const queryTerms = query
      .split(/\s+/)
      .filter((term) => term.length > 2);

    const matches = events.filter((event) => {
      const text = getEventText(event);
      const location = normalizeText(event.location);

      const directMatch = text.includes(query);
      const locationMatch = location && query.includes(location);
      const termMatch = queryTerms.some((term) => text.includes(term));

      return directMatch || locationMatch || termMatch;
    });

    setMatchedEvents(matches);
    setSimulation(null);
    setSearchMessage(
      matches.length > 0
        ? `Found ${matches.length} matching Agent 1 event${matches.length === 1 ? "" : "s"}. Simulation will also use Agents 2, 3, and 4.`
        : "No matching agent events found. You can still run a what-if simulation from the prompt."
    );
  }

  async function runSimulation() {
    if (!prompt.trim()) {
      setSearchMessage("Enter a prompt before simulating.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API}/simulate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt,
          matched_events: matchedEvents,
        }),
      });

      const data = await res.json();
      setSimulation(data);
      if (Array.isArray(data.agent_outputs)) {
        setAgents(data.agent_outputs);
      }
    } catch (error) {
      console.error("Simulation failed:", error);
      setSimulation(null);
      setSearchMessage("Simulation failed. Check that the FastAPI backend is running on port 8000.");
    } finally {
      setLoading(false);
    }
  }

  async function submitVoiceAudio(audioBlob) {
    const form = new FormData();
    form.append("audio", audioBlob, "citisim-voice.webm");
    form.append("matched_events", JSON.stringify(matchedEvents));
    form.append("fallback_prompt", prompt);

    setVoiceLoading(true);
    setLoading(true);
    setSearchMessage("Agent 5 is transcribing your voice and sending it through the simulation agents.");

    try {
      const res = await fetch(`${API}/voice/simulate`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || "Voice simulation failed.");
      }

      const data = await res.json();
      setPrompt(data.transcript || prompt);
      setSimulation(data.simulation);

      if (Array.isArray(data.simulation?.agent_outputs)) {
        setAgents(data.simulation.agent_outputs);
      }

      if (data.audio_base64) {
        const audio = new Audio(`data:${data.content_type || "audio/mpeg"};base64,${data.audio_base64}`);
        audio.play().catch((error) => {
          console.error("Voice playback failed:", error);
          setSearchMessage("Simulation finished, but the browser blocked audio playback.");
        });
      }

      setSearchMessage(
        data.warning ||
          "Simulation finished. Agent 5 read the recommendation response aloud."
      );
    } catch (error) {
      console.error("Voice simulation failed:", error);
      setSearchMessage(
        "Voice simulation failed. Check the FastAPI backend and ElevenLabs API key, or type the prompt and press Simulate."
      );
    } finally {
      setVoiceLoading(false);
      setLoading(false);
    }
  }

  async function startVoiceCapture() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setSearchMessage("Voice recording is not available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      audioChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data?.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        mediaRecorderRef.current = null;

        if (audioBlob.size > 0) {
          submitVoiceAudio(audioBlob);
        } else {
          setSearchMessage("No voice audio was captured.");
        }
      };

      recorder.start();
      setRecording(true);
      setSearchMessage("Listening. Press Stop when you are finished speaking.");
    } catch (error) {
      console.error("Could not start microphone:", error);
      setSearchMessage("Could not access your microphone. Allow microphone permissions and try again.");
    }
  }

  function stopVoiceCapture() {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setRecording(false);
  }

  function toggleVoiceCapture() {
    if (recording) {
      stopVoiceCapture();
    } else {
      startVoiceCapture();
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">Urban Operations Track</p>
        <h1>CitiSim</h1>
        <p>Search agent data, run what-if simulations, and preview operational impacts.</p>
        {dataSource && (
          <span className={`source-badge source-${dataSource.type}`}>
            {dataSource.type === "postgres" ? "Live event store" : dataSource.type.replaceAll("_", " ")}
          </span>
        )}
      </header>

      <section className="stats-row">
        <div className="stat-card">
          <span>Agent 1 Events</span>
          <strong>{totalEvents}</strong>
        </div>
        <div className="stat-card">
          <span>Matched Events</span>
          <strong>{matchedEvents.length}</strong>
        </div>
        <div className="stat-card">
          <span>High Severity</span>
          <strong>{highSeverityCount}</strong>
        </div>
        <div className="stat-card">
          <span>Active Agents</span>
          <strong>{activeAgentCount}/5</strong>
        </div>
      </section>

      <section className="agent-overview">
        <div className="panel-header">
          <h2>Agent Outputs</h2>
          <span>Agents 1-5 active</span>
        </div>

        <div className="agent-grid">
          {agents.map((agent) => (
            <AgentCard agent={agent} key={agent.id} />
          ))}
        </div>
      </section>

      <section className="simulator">
        <div className="section-heading">
          <h2>Run City Simulation</h2>
          <p>
            Search existing agent outputs, then simulate how the scenario may affect
            traffic, footfall, air quality, public transport, and local businesses.
          </p>
        </div>

        <div className="prompt-row">
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") searchPrompt();
            }}
            placeholder="Example: transport disruption at Farringdon during rain"
          />

          <button type="button" onClick={searchPrompt}>
            Search
          </button>

          <button type="button" onClick={runSimulation} disabled={loading}>
            {loading ? "Simulating..." : "Simulate"}
          </button>

          <button
            type="button"
            className={`voice-button ${recording ? "recording" : ""}`}
            onClick={toggleVoiceCapture}
            disabled={voiceLoading}
          >
            {recording ? "Stop" : voiceLoading ? "Voice..." : "Speak"}
          </button>
        </div>

        {searchMessage && <p className="helper-text">{searchMessage}</p>}
      </section>

      <section className="results">
        <div className="panel">
          <div className="panel-header">
            <h2>Matched Agent Data</h2>
            <span>{matchedEvents.length} shown</span>
          </div>

          {matchedEvents.length === 0 ? (
            <div className="empty-state">
              No matched events yet. Try searching for Liverpool Street, Bank,
              Farringdon, roadworks, transport, air quality, or footfall.
            </div>
          ) : (
            <div className="event-list">
              {matchedEvents.slice(0, 20).map((event, index) => (
                <EventCard event={event} key={event.id || index} />
              ))}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>Simulation Result</h2>
            {simulation && <span>{simulation.location}</span>}
          </div>

          {!simulation ? (
            <div className="empty-state">
              Run a simulation to generate an impact chart and operational recommendations.
            </div>
          ) : (
            <>
              <p className="summary">{simulation.summary}</p>

              {simulation.evidence && (
                <div className="evidence-strip">
                  <div>
                    <span>Evidence Events</span>
                    <strong>{simulation.evidence.context_event_count}</strong>
                  </div>
                  <div>
                    <span>Relationship Edges</span>
                    <strong>{simulation.evidence.relationship_edges}</strong>
                  </div>
                  <div>
                    <span>Forecast Points</span>
                    <strong>{simulation.evidence.forecast_points}</strong>
                  </div>
                  <div>
                    <span>Nemotron</span>
                    <strong>{simulation.nemotron_used ? "Used" : "Offline"}</strong>
                  </div>
                </div>
              )}

              {simulation.detected_factors?.length > 0 && (
                <div className="factor-row">
                  {simulation.detected_factors.map((factor) => (
                    <span key={factor}>{factor}</span>
                  ))}
                </div>
              )}

              <div className="chart">
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart data={simulation.chart}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="factor" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 100]} />
                    <Tooltip />
                    <Bar dataKey="impact" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {simulation.timeline?.length > 0 && (
                <>
                  <h3>Forecast Timeline</h3>
                  <div className="chart line-chart">
                    <ResponsiveContainer width="100%" height={340}>
                      <LineChart data={simulation.timeline}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" tick={{ fontSize: 12 }} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                        <Tooltip />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="congestion"
                          name="Congestion"
                          stroke="#0067a8"
                          strokeWidth={3}
                          dot={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="footfall"
                          name="Footfall"
                          stroke="#107f55"
                          strokeWidth={3}
                          dot={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="airQuality"
                          name="Air quality"
                          stroke="#b4233a"
                          strokeWidth={3}
                          dot={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="cycleDemand"
                          name="Cycle demand"
                          stroke="#946300"
                          strokeWidth={3}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </>
              )}

              <h3>Agent Recommendations</h3>
              <div className="recommendations">
                {simulation.recommendations?.map((rec, index) => (
                  <RecommendationCard recommendation={rec} key={rec.id || index} />
                ))}
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
