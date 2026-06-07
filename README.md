# CitiPulse

CitiPulse is a multi-agent urban operations intelligence platform that turns live city data into forecasts, relationships, and operational recommendations. The project combines Python agents, a FastAPI backend, and React/Vite frontends to help teams explore city disruptions, simulate scenarios, and review actionable insights.

## What this project does

- Ingests live/open city feeds such as transport, weather, air quality, footfall, and planning data.
- Builds agent-driven insights for disruption detection, relationship discovery, and forecasting.
- Runs scenario simulations to estimate how events may affect congestion, footfall, transport, and business activity.
- Exposes the results through a web dashboard and API for quick exploration.

## Core architecture

- `agents/` — Python agents for data intelligence, relationship discovery, forecasting, recommendations, and voice operations.
- `backend/` — FastAPI service that serves events, forecasts, recommendations, and simulation results.
- `frontend/` — main React/Vite dashboard used to search, visualize, and simulate city events.
- `urban-pulse-ui/` — a second Vite/React interface for the same Urban Pulse experience.
- `data/` — stored events, raw feeds, forecasts, and recommendation outputs.
- `memory/` — PostgreSQL schema and event-store helpers.
- `gpu/` — optional GPU-aware processing helpers.

## Tech stack

- Python 3.10+
- FastAPI + Uvicorn
- React + Vite
- Recharts for charts
- SQLAlchemy / PostgreSQL support
- Optional GPU helpers for accelerated processing

## Quick start

### 1) Create and activate a Python environment

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3) Start the backend

```bash
cd CitiPulse/backend
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

### 4) Start the frontend

```bash
cd ../frontend
npm install
npm run dev
```

The dashboard will be available at the Vite dev URL shown in the terminal.

## Useful API endpoints

- `GET /events` — current event feed
- `GET /agents` — agent output summary
- `GET /relationships` — relationship graph insights
- `GET /forecasts` — forecast output
- `GET /recommendations` — recommendation list
- `POST /simulate` — run a scenario simulation from a prompt

## Project folders

```text
CitiPulse/
  agents/          # agent pipeline and intelligence modules
  backend/         # FastAPI API layer
  data/            # event, forecast, and recommendation data
  frontend/        # primary React dashboard
  gpu/             # optional GPU helpers
  memory/          # PostgreSQL schema and storage helpers
  scripts/         # utility and orchestration scripts
  urban-pulse-ui/   # alternative React/Vite UI
```

## Notes

- The main dashboard uses Agents 1–4 in the UI.
- The project includes an additional voice/operations agent in `agents/agent5_voice_operations/`, which can be extended in future iterations.
- If you need live ingestion, use the backend refresh endpoint or run the agent pipeline from the included scripts.

## License

This project is distributed under the repository license in the `LICENSE` file.
