import { useEffect, useMemo, useRef, useState } from "react";
import "./style.css";

const API = import.meta.env.VITE_API_URL || "";

const PROMPT_CHIPS = [
  "Rain near Farringdon",
  "Transport disruption at Bank",
  "High footfall near Liverpool Street",
  "Poor air quality near Moorgate",
];

const METRIC_LINES = [
  { key: "congestion", name: "Traffic", color: "#22d3ee" },
  { key: "footfall", name: "Footfall", color: "#34d399" },
  { key: "airQuality", name: "Air quality", color: "#fb7185" },
  { key: "publicTransport", name: "Public transport", color: "#a78bfa" },
  { key: "businessImpact", name: "Local activity", color: "#facc15" },
  { key: "cycleDemand", name: "Cycling", color: "#fb923c" },
];

function normalizeText(value) {
  return String(value || "").toLowerCase();
}

function prettify(value, fallback = "Unknown") {
  if (!value) return fallback;

  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function cleanUserText(value) {
  return String(value || "")
    .replace(/Agent\s*1/gi, "the data layer")
    .replace(/Agent\s*2/gi, "the relationship model")
    .replace(/Agent\s*3/gi, "the scenario model")
    .replace(/Agent\s*4/gi, "the recommendation model")
    .replace(/Agent\s*5/gi, "the voice assistant")
    .replace(/simulation agents/gi, "the simulation system")
    .replace(/agent outputs/gi, "city intelligence")
    .replace(/agents/gi, "systems")
    .replace(/agent/gi, "system");
}

function clampPercent(value) {
  const number = Number(value);

  if (Number.isNaN(number)) return 0;

  return Math.max(0, Math.min(100, Math.round(number)));
}

function shortMetricLabel(value) {
  const label = prettify(value, "");

  const replacements = {
    "Public Transport": "Public transport",
    "Local Business": "Local activity",
    "Business Disruption": "Local activity",
    "Cycle Demand Drop": "Cycling impact",
    "Air Quality": "Air quality",
  };

  return replacements[label] || label;
}

function getEventText(event) {
  return `
    ${event.location || ""}
    ${event.location_name || ""}
    ${event.location_id || ""}
    ${event.event_type || ""}
    ${event.category || ""}
    ${event.severity || ""}
    ${event.summary || ""}
    ${event.description || ""}
    ${event.title || ""}
    ${event.action || ""}
  `.toLowerCase();
}

function getEventLocation(event) {
  return (
    event.location ||
    event.location_name ||
    event.station_name ||
    event.site_name ||
    event.borough ||
    event.location_id ||
    "Unknown location"
  );
}

function getDataStatus(dataSource) {
  if (!dataSource) return "Connecting";
  if (dataSource.type === "empty") return "No live feed";
  if (dataSource.type === "json_fallback") return "Saved data";
  if (dataSource.type === "postgres") return "Live data";

  return prettify(dataSource.type, "Data connected");
}

function EmptyState({ title, text, onPickPrompt }) {
  return (
    <div className="empty-state">
      <div>
        <strong>{title}</strong>
        <p>{text}</p>

        {onPickPrompt && (
          <div className="empty-chips">
            {PROMPT_CHIPS.map((chip) => (
              <button type="button" key={chip} onClick={() => onPickPrompt(chip)}>
                {chip}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function averageMetric(rows, key, defaultValue) {
  if (!rows.length) return defaultValue;

  const values = rows
    .map((row) => Number(row?.[key]))
    .filter((value) => !Number.isNaN(value));

  if (!values.length) return defaultValue;

  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  return clampPercent(average <= 1 ? average * 100 : average);
}

function normalizeTimelinePoint(point, index) {
  return {
    time: point.time || point.timestamp?.split?.("T")?.[1]?.slice(0, 5) || `T+${index + 1}`,
    congestion: clampPercent(point.congestion ?? Number(point.congestion_risk) * 100),
    footfall: clampPercent(point.footfall ?? Number(point.footfall_pressure) * 100),
    airQuality: clampPercent(point.airQuality ?? Number(point.air_quality_risk) * 100),
    publicTransport: clampPercent(point.publicTransport ?? Number(point.congestion_risk) * 100),
    businessImpact: clampPercent(point.businessImpact ?? Number(point.footfall_pressure) * 100),
    cycleDemand: clampPercent(point.cycleDemand ?? Number(point.cycle_demand) * 100),
  };
}

function RecommendationCard({ recommendation }) {
  if (typeof recommendation === "string") {
    return (
      <article className="rec priority-medium">
        <div className="rec-top">
          <span className="priority-badge">Medium priority</span>
        </div>

        <strong>{cleanUserText(recommendation)}</strong>
      </article>
    );
  }

  const priority = recommendation.priority || "medium";

  return (
    <article className={`rec priority-${priority}`}>
      <div className="rec-top">
        <span className="priority-badge">{prettify(priority)} priority</span>
      </div>

      <strong>
        {cleanUserText(
          recommendation.title ||
            recommendation.action ||
            "Recommended operational action"
        )}
      </strong>

      {recommendation.action && <p>{cleanUserText(recommendation.action)}</p>}
    </article>
  );
}

function ImpactBarGraph({ data }) {
  return (
    <div className="impact-bars">
      {data.map((item) => (
        <div className="impact-row" key={item.factor}>
          <div className="impact-label">
            <span>{item.factor}</span>
            <strong>{item.impact}%</strong>
          </div>
          <div className="impact-track" aria-hidden="true">
            <span style={{ width: `${item.impact}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function ForecastLineGraph({ data, metrics }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const svgRef = useRef(null);
  const width = 760;
  const height = 320;
  const padding = { top: 28, right: 26, bottom: 46, left: 46 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const pointCount = Math.max(data.length - 1, 1);
  const gridTicks = [0, 25, 50, 75, 100];

  function x(index) {
    return padding.left + (index / pointCount) * innerWidth;
  }

  function y(value) {
    return padding.top + (1 - clampPercent(value) / 100) * innerHeight;
  }

  function pathFor(metric) {
    return data
      .map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(point[metric.key])}`)
      .join(" ");
  }

  function updateHover(event) {
    const bounds = svgRef.current?.getBoundingClientRect();

    if (!bounds) return;

    const relativeX = ((event.clientX - bounds.left) / bounds.width) * width;
    const rawIndex = Math.round(((relativeX - padding.left) / innerWidth) * pointCount);
    const nextIndex = Math.max(0, Math.min(data.length - 1, rawIndex));

    setHoverIndex(nextIndex);
  }

  const hoverPoint = hoverIndex === null ? null : data[hoverIndex];
  const hoverX = hoverIndex === null ? null : x(hoverIndex);

  return (
    <div className="timeline-graph">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Forecast timeline chart"
        onMouseMove={updateHover}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {gridTicks.map((tick) => (
          <g key={tick}>
            <line
              className="grid-line"
              x1={padding.left}
              x2={width - padding.right}
              y1={y(tick)}
              y2={y(tick)}
            />
            <text className="axis-label" x={12} y={y(tick) + 4}>
              {tick}%
            </text>
          </g>
        ))}

        {data.map((point, index) => {
          if (index % Math.ceil(data.length / 6) !== 0 && index !== data.length - 1) {
            return null;
          }

          return (
            <text className="axis-label" key={`${point.time}-${index}`} x={x(index)} y={height - 14} textAnchor="middle">
              {point.time}
            </text>
          );
        })}

        {metrics.map((metric) => (
          <path
            className="metric-line"
            d={pathFor(metric)}
            key={metric.key}
            stroke={metric.color}
          />
        ))}

        {metrics.map((metric) =>
          data.map((point, index) => (
            <circle
              className="metric-point"
              cx={x(index)}
              cy={y(point[metric.key])}
              fill={metric.color}
              key={`${metric.key}-${index}`}
              r="3"
            />
          ))
        )}

        {hoverPoint && (
          <>
            <line
              className="hover-line"
              x1={hoverX}
              x2={hoverX}
              y1={padding.top}
              y2={height - padding.bottom}
            />

            {metrics.map((metric) => (
              <circle
                className="hover-point"
                cx={hoverX}
                cy={y(hoverPoint[metric.key])}
                fill={metric.color}
                key={`hover-${metric.key}`}
                r="5"
              />
            ))}
          </>
        )}
      </svg>

      {hoverPoint && (
        <div className="line-hover-card">
          <strong>{hoverPoint.time}</strong>
          <div>
            {metrics.map((metric) => (
              <span key={metric.key}>
                <i style={{ background: metric.color }} />
                {metric.name}
                <b>{clampPercent(hoverPoint[metric.key])}%</b>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="chart-legend">
        {metrics.map((metric) => (
          <span key={metric.key}>
            <i style={{ background: metric.color }} />
            {metric.name}
          </span>
        ))}
      </div>
    </div>
  );
}

async function errorMessageFromResponse(res) {
  const text = await res.text();
  if (!text) return "Voice simulation failed.";

  try {
    const payload = JSON.parse(text);
    return payload.detail || payload.message || text;
  } catch {
    return text;
  }
}

export default function App() {
  const [prompt, setPrompt] = useState("");
  const [events, setEvents] = useState([]);
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

    async function loadCityData() {
      try {
        const [eventsRes, sourceRes] = await Promise.all([
          fetch(`${API}/events`),
          fetch(`${API}/data-source`),
        ]);

        if (!eventsRes.ok || !sourceRes.ok) {
          throw new Error("City data request failed.");
        }

        const eventsData = await eventsRes.json();
        const sourceData = await sourceRes.json();

        if (!cancelled) {
          setEvents(Array.isArray(eventsData) ? eventsData : []);
          setDataSource(sourceData);
        }
      } catch (error) {
        console.error("Failed to load city data:", error);

        if (!cancelled) {
          setEvents([]);
          setDataSource(null);
          setSearchMessage("Could not connect to the city data service.");
        }
      }
    }

    loadCityData();

    return () => {
      cancelled = true;
    };
  }, []);

  const totalEvents = events.length;

  const highSeverityCount = useMemo(
    () => events.filter((event) => event.severity === "high").length,
    [events]
  );

  const locationCount = useMemo(() => {
    return new Set(events.map(getEventLocation).filter(Boolean)).size;
  }, [events]);

  const dataStatus = getDataStatus(dataSource);
  const scenarioTitle = simulation?.location || (prompt.trim() ? "Scenario results" : "No scenario selected yet");
  const hasScenarioActivity = loading || Boolean(simulation) || Boolean(searchMessage) || matchedEvents.length > 0;

  const impactChartData = useMemo(() => {
    const chartRows =
      (Array.isArray(simulation?.chart) && simulation.chart) ||
      (Array.isArray(simulation?.scenario_delta?.chart) && simulation.scenario_delta.chart) ||
      [];

    if (chartRows.length > 0) {
      return chartRows
        .filter((item) => item && item.factor)
        .map((item) => ({
          factor: shortMetricLabel(item.factor),
          impact: clampPercent(item.impact),
        }));
    }

    const forecastRows = Array.isArray(simulation?.forecast?.forecast)
      ? simulation.forecast.forecast
      : [];

    if (!forecastRows.length) return [];

    return [
      { factor: "Traffic", impact: averageMetric(forecastRows, "congestion_risk", 35) },
      { factor: "Footfall", impact: averageMetric(forecastRows, "footfall_pressure", 30) },
      { factor: "Air quality", impact: averageMetric(forecastRows, "air_quality_risk", 25) },
      { factor: "Public transport", impact: averageMetric(forecastRows, "congestion_risk", 28) },
      { factor: "Cycling impact", impact: 100 - averageMetric(forecastRows, "cycle_demand", 55) },
    ];
  }, [simulation]);

  const timelineData = useMemo(() => {
    const rows =
      (Array.isArray(simulation?.timeline) && simulation.timeline) ||
      (Array.isArray(simulation?.forecast?.timeline) && simulation.forecast.timeline) ||
      (Array.isArray(simulation?.forecast?.forecast) && simulation.forecast.forecast) ||
      [];

    return rows.map(normalizeTimelinePoint);
  }, [simulation]);

  const activeMetricLines = useMemo(() => {
    if (!timelineData.length) return METRIC_LINES.slice(0, 4);

    const activeLines = METRIC_LINES.map((metric) => ({
      ...metric,
      total: timelineData.reduce((sum, point) => sum + Number(point[metric.key] || 0), 0),
    }))
      .filter((metric) => metric.total > 0)
      .sort((a, b) => b.total - a.total)
      .slice(0, 4);

    return activeLines.length > 0 ? activeLines : METRIC_LINES.slice(0, 4);
  }, [timelineData]);

  const recommendations = Array.isArray(simulation?.recommendations)
    ? simulation.recommendations
    : [];

  function applyPromptChip(chip) {
    setPrompt(chip);
    setSimulation(null);
    setSearchMessage("");
  }

  function searchPrompt() {
    const query = normalizeText(prompt).trim();

    if (!query) {
      setMatchedEvents([]);
      setSimulation(null);
      setSearchMessage("Enter a city scenario before searching.");
      return;
    }

    const queryTerms = query.split(/\s+/).filter((term) => term.length > 2);

    const matches = events.filter((event) => {
      const text = getEventText(event);
      const location = normalizeText(getEventLocation(event));

      const directMatch = text.includes(query);
      const locationMatch = location && query.includes(location);
      const termMatch = queryTerms.some((term) => text.includes(term));

      return directMatch || locationMatch || termMatch;
    });

    setMatchedEvents(matches);
    setSimulation(null);

    setSearchMessage(
      matches.length > 0
        ? `Found ${matches.length} relevant city signal${matches.length === 1 ? "" : "s"}.`
        : "No exact match found. You can still test the scenario."
    );
  }

  async function runSimulation() {
    if (!prompt.trim()) {
      setSearchMessage("Enter a city scenario before simulating.");
      return;
    }

    setLoading(true);
    setSearchMessage("Running scenario model...");

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

      if (!res.ok) {
        throw new Error("Simulation request failed.");
      }

      const data = await res.json();

      setSimulation(data);
      setSearchMessage("Scenario ready. Review the impacts and recommended actions.");
    } catch (error) {
      console.error("Simulation failed:", error);
      setSimulation(null);
      setSearchMessage("Simulation failed. Check that the city operations backend is running.");
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
    setSearchMessage("Analysing your voice scenario...");

    try {
      const res = await fetch(`${API}/voice/simulate`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        throw new Error(await errorMessageFromResponse(res));
      }

      const data = await res.json();
      const nextSimulation = data.simulation || data;

      setPrompt(data.transcript || prompt);
      setSimulation(nextSimulation);

      if (data.audio_base64) {
        const audio = new Audio(
          `data:${data.content_type || "audio/mpeg"};base64,${data.audio_base64}`
        );

        audio.play().catch((error) => {
          console.error("Voice playback failed:", error);
          setSearchMessage("Scenario ready, but the browser blocked audio playback.");
        });
      }

      setSearchMessage(data.warning || "Scenario ready. Recommended actions have been generated.");
    } catch (error) {
      console.error("Voice simulation failed:", error);
      setSearchMessage("Voice simulation failed. Type the scenario and press Simulate.");
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
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });

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
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Urban Operations Command Centre</p>
          <h1>CitiSim</h1>
          <p>Urban scenario intelligence for live city operations.</p>
        </div>

        <div className="scenario-console">
          <div className="console-top">
            <div>
              <span>Test a city scenario</span>
            </div>

            <span className={`status-pill ${dataSource?.type === "empty" ? "offline" : "online"}`}>
              {dataStatus}
            </span>
          </div>

          <div className="prompt-row">
            <input
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") searchPrompt();
              }}
              placeholder="Transport disruption at Farringdon during rain"
            />

            <button type="button" className="secondary-button" onClick={searchPrompt}>
              Search
            </button>

            <button type="button" onClick={runSimulation} disabled={loading}>
              {loading ? "Running..." : "Simulate"}
            </button>

            <button
              type="button"
              className={`voice-button ${recording ? "recording" : ""}`}
              onClick={toggleVoiceCapture}
              disabled={voiceLoading}
            >
              {recording ? "Stop" : voiceLoading ? "Listening..." : "Speak"}
            </button>
          </div>

          <div className="prompt-chips" aria-label="Suggested scenarios">
            <span>Try</span>

            {PROMPT_CHIPS.map((chip) => (
              <button type="button" key={chip} onClick={() => applyPromptChip(chip)}>
                {chip}
              </button>
            ))}
          </div>

          {(searchMessage || loading) && (
            <div className={`helper-text ${loading ? "loading" : ""}`}>
              {loading && <span className="spinner" />}
              <span>{searchMessage || "Analysing city signals..."}</span>
            </div>
          )}
        </div>
      </section>

      {hasScenarioActivity && (
        <section className="scenario-output">
          <article className="panel result-panel">
            <div className="panel-header">
              <div>
                <span>Scenario result</span>
                <h2>{scenarioTitle}</h2>
              </div>
            </div>

            {!simulation ? (
              <EmptyState
                title={loading ? "Running scenario model..." : "No simulation result yet"}
                text={
                  loading
                    ? "Analysing city signals and preparing recommended actions."
                    : "Press Simulate to generate the impact overview, forecast timeline, and actions."
                }
                onPickPrompt={!loading ? applyPromptChip : undefined}
              />
            ) : (
              <>
                <p className="summary">{cleanUserText(simulation.summary)}</p>

                <div className="evidence-strip">
                  <div>
                    <span>Evidence used</span>
                    <strong>{simulation.evidence?.context_event_count ?? matchedEvents.length}</strong>
                  </div>

                  <div>
                    <span>Forecast horizon</span>
                    <strong>{timelineData.length} steps</strong>
                  </div>

                  <div>
                    <span>Advisor</span>
                    <strong>{simulation.nemotron_used ? "Online" : "Standard"}</strong>
                  </div>
                </div>

                {simulation.detected_factors?.length > 0 && (
                  <div className="factor-row">
                    {simulation.detected_factors.map((factor) => (
                      <span key={factor}>{prettify(factor)}</span>
                    ))}
                  </div>
                )}
              </>
            )}
          </article>

          {simulation && (
            <>
              <section className="charts-grid priority-charts">
                <article className="panel chart-block">
                  <div className="chart-title">
                    <div>
                      <h2>Impact overview</h2>
                      <p>Projected pressure across operational areas.</p>
                    </div>

                    <span>0-100%</span>
                  </div>

                  {impactChartData.length === 0 ? (
                    <EmptyState
                      title="No impact data"
                      text="The scenario completed, but no impact chart values were returned."
                    />
                  ) : (
                    <div className="chart horizontal-chart">
                      <ImpactBarGraph data={impactChartData} />
                    </div>
                  )}
                </article>

                <article className="panel chart-block">
                  <div className="chart-title">
                    <div>
                      <h2>Forecast timeline</h2>
                      <p>Projected city conditions over the scenario window.</p>
                    </div>

                    <span>Top signals</span>
                  </div>

                  {timelineData.length === 0 ? (
                    <EmptyState
                      title="No timeline data"
                      text="The scenario completed, but no forecast timeline was returned."
                    />
                  ) : (
                    <div className="chart line-chart">
                      <ForecastLineGraph data={timelineData} metrics={activeMetricLines} />
                    </div>
                  )}
                </article>
              </section>

              <section className="panel actions-panel priority-actions">
                <div className="panel-header">
                  <div>
                    <span>Recommended actions</span>
                    <h2>What to do next</h2>
                  </div>

                  <strong>{recommendations.length} actions</strong>
                </div>

                {recommendations.length === 0 ? (
                  <EmptyState
                    title="No recommendations generated"
                    text="Try running the scenario again or add more matching city signals."
                  />
                ) : (
                  <div className="recommendations">
                    {recommendations.map((rec, index) => (
                      <RecommendationCard recommendation={rec} key={rec.id || index} />
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </section>
      )}

      <section className="status-strip">
        <span>{dataStatus}</span>
        <span>{totalEvents} city signals</span>
        <span>{locationCount} locations monitored</span>
      </section>

      <section className="stats-row" aria-label="Live city snapshot">
        <article className="stat-card">
          <span className="stat-dot cyan" />
          <strong>{totalEvents}</strong>
          <div>
            <span>City signals</span>
            <p>{dataStatus}</p>
          </div>
        </article>

        <article className="stat-card">
          <span className="stat-dot coral" />
          <strong>{highSeverityCount}</strong>
          <div>
            <span>High priority</span>
            <p>Needs attention</p>
          </div>
        </article>

        <article className="stat-card">
          <span className="stat-dot violet" />
          <strong>{locationCount}</strong>
          <div>
            <span>Locations</span>
            <p>Across the network</p>
          </div>
        </article>

        <article className="stat-card">
          <span className="stat-dot emerald" />
          <strong>{matchedEvents.length}</strong>
          <div>
            <span>Matches</span>
            <p>Search results</p>
          </div>
        </article>
      </section>

      {loading && (
        <section className="loading-panel">
          <span className="spinner" />
          <div>
            <strong>Running scenario model...</strong>
            <p>Analysing city signals and preparing recommended actions.</p>
          </div>
        </section>
      )}
    </main>
  );
}