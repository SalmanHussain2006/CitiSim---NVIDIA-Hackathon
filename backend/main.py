from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path

app = FastAPI(title="Urban Pulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path(__file__).resolve().parents[1]

def latest_json(folder, prefix=None):
    files = list((BASE / folder).glob("*.json"))
    if prefix:
        files = [f for f in files if f.name.startswith(prefix)]
    if not files:
        return None
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return json.loads(latest.read_text(encoding="utf-8"))

@app.get("/")
def root():
    return {"status": "Urban Pulse backend running"}

@app.get("/events")
def events():
    data = latest_json("data/events", "agent1_events")
    return data or []

@app.get("/relationships")
def relationships():
    return latest_json("data/processed", "relationships") or {}

@app.get("/forecasts")
def forecasts():
    return latest_json("data/forecasts") or {}

@app.get("/recommendations")
def recommendations():
    return latest_json("data/recommendations") or {}