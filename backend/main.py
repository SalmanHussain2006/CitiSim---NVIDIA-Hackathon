from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
from pathlib import Path

from agents.agent2_relationship_discovery.agent2 import run_agent2
from agents.agent3_forecast_simulation.agent3 import run_agent3
from agents.agent3_forecast_simulation.congestion_forecaster import adapt_agent_events
from agents.agent4_recommendation.agent4 import generate_forecast_recommendations, generate_recommendations
from agents.agent5_voice_operations.agent5 import (
    VoiceAgentError,
    recommendation_script,
    synthesize_speech,
    transcribe_audio,
)

app = FastAPI(title="CitiSim API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path(__file__).resolve().parents[1]
EVENT_SOURCE = {"type": "unknown", "detail": "No event source loaded."}


class SimulationRequest(BaseModel):
    prompt: str
    matched_events: list = Field(default_factory=list)


class SpeechRequest(BaseModel):
    text: str


def latest_json(folder, prefix=None):
    files = list((BASE / folder).glob("*.json"))

    if prefix:
        files = [f for f in files if f.name.startswith(prefix)]

    if not files:
        return None

    latest = max(files, key=lambda f: f.stat().st_mtime)
    return json.loads(latest.read_text(encoding="utf-8"))


def db_row_to_event(row):
    raw = row.get("raw_json")
    if isinstance(raw, dict):
        event = dict(raw)
    else:
        event = {}

    event_id = row.get("event_id") or event.get("event_id") or event.get("id")
    event_type = row.get("event_type") or event.get("event_type") or "unknown"
    location_id = row.get("location_id") or event.get("location_id") or "unknown"
    start_time = row.get("start_time") or event.get("start_time") or event.get("timestamp")
    impact_score = row.get("impact_score", event.get("impact_score", event.get("value", 0.5)))
    confidence = row.get("confidence", event.get("confidence", 0.7))

    event.update(
        {
            "id": event.get("id") or event_id,
            "event_id": event_id,
            "event_type": event_type,
            "location_id": location_id,
            "start_time": str(start_time),
            "impact_score": impact_score,
            "duration_minutes": row.get("duration_minutes", event.get("duration_minutes", 60)),
            "confidence": confidence,
            "location": event.get("location") or str(location_id).replace("_", " ").title(),
            "severity": event.get("severity") or score_to_severity(impact_score),
            "summary": event.get("summary") or row.get("description") or f"{event_type} detected at {location_id}",
            "source_agent": event.get("source_agent") or row.get("source") or "agent_1_data_intelligence",
        }
    )

    return event


def score_to_severity(score):
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "medium"

    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def load_current_events(limit=500):
    global EVENT_SOURCE

    try:
        from storage import init_db, recent_events_full

        conn = init_db()
        try:
            rows = recent_events_full(conn, limit=limit)
        finally:
            conn.close()

        if rows:
            EVENT_SOURCE = {
                "type": "postgres",
                "detail": f"Loaded {len(rows)} recent events from the shared event store.",
            }
            return [db_row_to_event(row) for row in rows]
    except Exception as error:
        EVENT_SOURCE = {
            "type": "json_fallback",
            "detail": f"Postgres unavailable; using latest Agent 1 JSON batch. Reason: {error}",
        }

    data = latest_json("data/events", "agent1_events") or []
    if data:
        EVENT_SOURCE = {
            "type": "json_fallback",
            "detail": "Loaded latest saved Agent 1 JSON batch from data/events.",
        }
    else:
        EVENT_SOURCE = {
            "type": "empty",
            "detail": "No Postgres events or Agent 1 JSON batch found.",
        }
    return data


def infer_location(prompt, matched_events):
    text = prompt.lower()
    known_locations = {
        "liverpool": "Liverpool Street",
        "bank": "Bank",
        "farringdon": "Farringdon",
        "moorgate": "Moorgate",
        "tower": "Tower Hill",
        "camden": "Camden High Street",
        "kings cross": "Kings Cross",
        "oxford": "Oxford Circus",
    }

    for keyword, location in known_locations.items():
        if keyword in text:
            return location

    if matched_events:
        return matched_events[0].get("location") or matched_events[0].get("location_id") or "City of London"

    return "City of London"


def slug(value):
    return str(value or "city_of_london").strip().lower().replace(" ", "_")


def infer_scenario(prompt):
    text = prompt.lower()
    if any(term in text for term in ["tube", "train", "station", "transport"]):
        return "station_disruption"
    if any(term in text for term in ["rain", "weather", "wind", "storm"]):
        return "heavy_rain"
    if any(term in text for term in ["planning", "development", "construction", "pedestrianised", "pedestrianized", "pedestrian"]):
        return "office_development"
    if any(term in text for term in ["road", "close", "closure", "roadworks", "traffic"]):
        return "roadworks"
    return "baseline"


def event_matches_prompt(event, prompt, location, scenario):
    text = " ".join(
        str(event.get(key, ""))
        for key in [
            "source_agent",
            "location",
            "location_id",
            "event_type",
            "severity",
            "summary",
            "title",
            "action",
        ]
    ).lower()
    terms = [term for term in prompt.lower().split() if len(term) > 2]
    scenario_terms = {
        "station_disruption": ["transport", "tube", "train", "station", "line"],
        "heavy_rain": ["weather", "rain", "storm", "flood", "wind"],
        "office_development": ["planning", "development", "construction", "footfall", "pedestrian"],
        "roadworks": ["road", "traffic", "roadworks", "closure", "disruption"],
        "baseline": [],
    }

    location_match = slug(location) in slug(event.get("location") or event.get("location_id"))
    term_match = any(term in text for term in terms)
    scenario_match = any(term in text for term in scenario_terms.get(scenario, []))

    return location_match or term_match or scenario_match


def select_context_events(prompt, all_events, location, scenario, limit=80):
    matches = [
        event
        for event in all_events
        if event_matches_prompt(event, prompt, location, scenario)
    ]

    return matches[:limit]


def scenario_recommendations(prompt, scenario, location, chart, timeline):
    top_factor = max(chart, key=lambda item: item["impact"]) if chart else {"factor": "city operations", "impact": 0}
    peak = max(timeline, key=lambda item: item.get("congestion", 0)) if timeline else {}
    peak_time = peak.get("time") or "the next operating window"

    templates = {
        "office_development": [
            (
                "pedestrian_flow",
                "high",
                f"Create a pedestrian-first operating plan for {location}",
                "Model temporary crossings, bus stop changes, delivery windows, and stewarding before approving the scheme.",
            ),
            (
                "business_access",
                "medium",
                f"Protect business access around {location}",
                "Publish loading bay alternatives and access windows for nearby shops, offices, and venues.",
            ),
        ],
        "station_disruption": [
            (
                "transport_resilience",
                "high",
                f"Prepare station diversion routes near {location}",
                "Coordinate TfL messaging, bus bridging, taxi ranks, and crowd control around exits before peak demand.",
            ),
            (
                "crowd_management",
                "medium",
                f"Reduce platform-to-street crowding near {location}",
                "Use live signage and staff deployment to split flows across nearby stations and quieter streets.",
            ),
        ],
        "heavy_rain": [
            (
                "weather_response",
                "high",
                f"Prepare wet-weather controls for {location}",
                "Prioritise drainage checks, sheltered queue plans, slower signal timings, and road incident monitoring.",
            ),
            (
                "public_messaging",
                "medium",
                f"Warn travellers about weather impact near {location}",
                "Push guidance for extra journey time, safer walking routes, and alternative cycle options.",
            ),
        ],
        "roadworks": [
            (
                "traffic_management",
                "high",
                f"Stage road closures around {location}",
                "Use phased lane restrictions, signed diversion routes, and bus-priority measures during the peak risk period.",
            ),
            (
                "network_coordination",
                "medium",
                f"Coordinate nearby works before traffic builds at {location}",
                "Pause non-critical permits nearby and monitor junction queues in real time.",
            ),
        ],
        "baseline": [
            (
                "operations_monitoring",
                "medium",
                f"Monitor the simulated pressure around {location}",
                "Keep live event, footfall, transport, and air-quality feeds under review while the scenario develops.",
            ),
        ],
    }

    recommendations = []
    for rec_type, priority, title, action in templates.get(scenario, templates["baseline"]):
        recommendations.append(
            {
                "id": f"rec_prompt_{slug(location)}_{scenario}_{rec_type}",
                "source_agent": "agent_4_recommendation",
                "location": location,
                "priority": priority,
                "recommendation_type": rec_type,
                "title": title,
                "action": action,
                "reasoning": [
                    f"The prompt was interpreted as {scenario.replace('_', ' ')}.",
                    f"The strongest simulated factor is {top_factor['factor']} at {top_factor['impact']}%.",
                    f"Peak congestion pressure is expected around {peak_time}.",
                    f"Original prompt: {prompt}",
                ],
                "predicted_outcome": {
                    "top_factor": top_factor["factor"],
                    "top_factor_impact": top_factor["impact"],
                    "peak_time": peak_time,
                },
                "source_event_ids": [],
            }
        )

    return recommendations


def dedupe_recommendations(recommendations):
    deduped = []
    seen = set()

    for recommendation in recommendations:
        if isinstance(recommendation, str):
            key = recommendation
        else:
            key = recommendation.get("id") or recommendation.get("title") or recommendation.get("action")

        if key in seen:
            continue

        seen.add(key)
        deduped.append(recommendation)

    return deduped


def impact_chart_from_forecast(forecast, location_id=None):
    rows = [
        point
        for point in forecast
        if not location_id or point.get("location_id") == location_id
    ] or forecast

    if not rows:
        rows = []

    def avg(key, default=0):
        if not rows:
            return default
        return round(sum(float(point.get(key, 0)) for point in rows) / len(rows) * 100)

    return [
        {"factor": "Traffic", "impact": avg("congestion_risk", 35)},
        {"factor": "Footfall", "impact": avg("footfall_pressure", 30)},
        {"factor": "Air Quality", "impact": avg("air_quality_risk", 25)},
        {"factor": "Public Transport", "impact": avg("congestion_risk", 28)},
        {"factor": "Cycle Demand Drop", "impact": round(100 - avg("cycle_demand", 55))},
    ]


def timeline_from_forecast(forecast, location_id=None):
    rows = [
        point
        for point in forecast
        if not location_id or point.get("location_id") == location_id
    ] or forecast

    timeline = []
    for point in rows:
        time_label = str(point.get("time", ""))
        if "T" in time_label:
            time_label = time_label.split("T", 1)[1][:5]

        timeline.append(
            {
                "time": time_label,
                "congestion": round(float(point.get("congestion_risk", 0)) * 100),
                "footfall": round(float(point.get("footfall_pressure", 0)) * 100),
                "airQuality": round(float(point.get("air_quality_risk", 0)) * 100),
                "cycleDemand": round(float(point.get("cycle_demand", 0)) * 100),
                "confidence": round(float(point.get("confidence", 0)) * 100),
            }
        )

    return timeline


def agent2_records(events_data):
    return adapt_agent_events(events_data).to_dict(orient="records")


def agent_payload(events_data=None, relationship_graph=None, forecast_payload=None, recommendations_payload=None):
    events_data = events_data if events_data is not None else load_current_events()
    relationship_graph = relationship_graph or run_agent2(agent2_records(events_data), min_active_buckets=1)
    forecast_payload = forecast_payload or run_agent3(
        records=events_data,
        horizon_hours=12,
        scenario="baseline",
        relationship_graph=relationship_graph,
    )
    recommendations_payload = recommendations_payload or {
        "recommendations": generate_recommendations(events_data)
        + generate_forecast_recommendations(forecast_payload)
    }

    return [
        {
            "id": "agent_1",
            "name": "Agent 1",
            "title": "Data Intelligence",
            "status": "active",
            "summary": "Normalises live/raw city signals into operational events.",
            "metric": len(events_data),
            "metric_label": "events",
            "source": EVENT_SOURCE,
            "items": events_data[:6],
        },
        {
            "id": "agent_2",
            "name": "Agent 2",
            "title": "Relationship Discovery",
            "status": "active",
            "summary": "Builds the city-impact relationship graph used by simulation.",
            "metric": relationship_graph.get("metadata", {}).get("edge_count", 0),
            "metric_label": "edges",
            "items": relationship_graph.get("insights", [])[:6],
        },
        {
            "id": "agent_3",
            "name": "Agent 3",
            "title": "Forecast Simulation",
            "status": "active",
            "summary": "Forecasts congestion, footfall, cycle demand, and air quality over time.",
            "metric": forecast_payload.get("metadata", {}).get("forecast_point_count", 0),
            "metric_label": "forecast points",
            "items": forecast_payload.get("alerts", [])[:6],
        },
        {
            "id": "agent_4",
            "name": "Agent 4",
            "title": "Recommendation",
            "status": "active",
            "summary": "Turns current events and forecasts into operational actions.",
            "metric": len(recommendations_payload.get("recommendations", [])),
            "metric_label": "actions",
            "items": recommendations_payload.get("recommendations", [])[:6],
        },
        {
            "id": "agent_5",
            "name": "Agent 5",
            "title": "Voice Operations",
            "status": "active",
            "summary": "Listens to operators, sends transcripts into simulation, and speaks recommendations.",
            "metric": 2,
            "metric_label": "voice modes",
            "items": [
                "Speech-to-text input through ElevenLabs.",
                "Text-to-speech recommendation playback after simulation.",
            ],
        },
    ]


@app.get("/")
def root():
    return {"status": "CitiSim backend running"}


@app.get("/events")
def events():
    return load_current_events()


@app.get("/agents")
def agents():
    events_data = load_current_events()
    return agent_payload(events_data=events_data)


@app.get("/data-source")
def data_source():
    load_current_events()
    return EVENT_SOURCE


@app.get("/relationships")
def relationships():
    return latest_json("data/processed", "relationships") or {}


@app.get("/forecasts")
def forecasts():
    return latest_json("data/forecasts") or {}


@app.get("/recommendations")
def recommendations():
    return latest_json("data/recommendations") or {}


@app.post("/simulate")
def simulate(req: SimulationRequest):
    prompt = req.prompt.lower()
    matched_events = req.matched_events or []
    all_events = load_current_events()
    location = infer_location(prompt, matched_events)
    location_id = slug(location)
    scenario = infer_scenario(prompt)
    context_events = matched_events or select_context_events(prompt, all_events, location, scenario) or all_events

    relationship_graph = run_agent2(agent2_records(context_events), min_active_buckets=1)
    forecast_payload = run_agent3(
        records=context_events,
        horizon_hours=12,
        scenario=scenario,
        scenario_location=location_id,
        relationship_graph=relationship_graph,
    )

    chart = impact_chart_from_forecast(forecast_payload.get("forecast", []), location_id)
    timeline = timeline_from_forecast(forecast_payload.get("forecast", []), location_id)
    top = max(chart, key=lambda x: x["impact"])

    recommendation_list = dedupe_recommendations(
        scenario_recommendations(req.prompt, scenario, location, chart, timeline)
        + generate_recommendations(context_events)
        + generate_forecast_recommendations(forecast_payload)
    )
    if not recommendation_list:
        recommendation_list = [
            {
                "title": "Increase monitoring around affected junctions and station exits.",
                "action": "Prepare temporary traffic management and pedestrian flow controls.",
                "priority": "medium",
            },
            {
                "title": "Notify nearby transport hubs, businesses, and operations teams.",
                "action": "Share the simulated risk window with duty managers.",
                "priority": "medium",
            },
        ]

    detected_factors = [scenario.replace("_", " ")]
    detected_factors.extend(
        alert.get("outcome", "").replace("_", " ")
        for alert in forecast_payload.get("alerts", [])[:4]
        if alert.get("outcome")
    )

    return {
        "location": location,
        "prompt": req.prompt,
        "matched_event_count": len(matched_events),
        "scenario": scenario,
        "detected_factors": list(dict.fromkeys(detected_factors)),
        "summary": f"Agent 3 predicts the highest simulated impact on {top['factor']} around {location}, using Agent 2 relationships and {len(context_events)} Agent 1 events.",
        "chart": chart,
        "timeline": timeline,
        "forecast": forecast_payload,
        "agent_outputs": agent_payload(
            events_data=all_events,
            relationship_graph=relationship_graph,
            forecast_payload=forecast_payload,
            recommendations_payload={"recommendations": recommendation_list},
        ),
        "recommendations": recommendation_list[:8],
    }


@app.post("/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    transcript = transcribe_audio(
        audio_bytes,
        filename=audio.filename or "voice.webm",
        content_type=audio.content_type or "audio/webm",
    )
    return {"transcript": transcript}


@app.post("/voice/speak")
def voice_speak(req: SpeechRequest):
    speech = synthesize_speech(req.text)
    return {
        "text": speech.text,
        "audio_base64": speech.audio_base64,
        "content_type": speech.content_type,
        "warning": speech.warning,
    }


@app.post("/voice/simulate")
async def voice_simulate(
    audio: UploadFile = File(...),
    matched_events: str = Form("[]"),
    fallback_prompt: str = Form(""),
):
    warning = ""
    audio_bytes = await audio.read()

    try:
        transcript = transcribe_audio(
            audio_bytes,
            filename=audio.filename or "voice.webm",
            content_type=audio.content_type or "audio/webm",
        )
    except VoiceAgentError as error:
        if not fallback_prompt.strip():
            raise
        transcript = fallback_prompt.strip()
        warning = f"Voice transcription unavailable; used typed prompt instead. {error}"

    try:
        matched = json.loads(matched_events)
        if not isinstance(matched, list):
            matched = []
    except json.JSONDecodeError:
        matched = []

    simulation = simulate(SimulationRequest(prompt=transcript, matched_events=matched))
    spoken_text = recommendation_script(simulation)

    try:
        speech = synthesize_speech(spoken_text)
        audio_base64 = speech.audio_base64
        content_type = speech.content_type
    except VoiceAgentError as error:
        audio_base64 = ""
        content_type = "audio/mpeg"
        warning = " ".join([warning, f"Voice response unavailable. {error}"]).strip()

    return {
        "transcript": transcript,
        "simulation": simulation,
        "spoken_text": spoken_text,
        "audio_base64": audio_base64,
        "content_type": content_type,
        "warning": warning,
    }
