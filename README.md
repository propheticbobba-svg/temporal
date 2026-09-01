# Temporal

Place intelligence. Submit an address, get a structured brief of public
signals over time — permits, business licenses, and whatever sources you
register next.

Facts live in `signals`. Briefs are derived from those facts and stored
until the source is stale. The request path does not refetch the world
on every click.

## Stack

- Backend: Python 3.11, FastAPI, SQLAlchemy, PostgreSQL
- Frontend: TypeScript, React, Vite, TanStack Query, Tailwind
- Ingestion: httpx against public APIs (Census, Socrata, optional permits)

## Layout

| Path | Role |
|---|---|
| `backend/app.py` | HTTP door |
| `backend/fetch/` | Talk to the world: geocode, licenses, permits, crime |
| `backend/place.py` | Identify a place, persist signals, decide what is stale |
| `backend/brief/` | Classify, graph, modules, snapshot |
| `backend/think.py` | Vertex copy fused onto existing ids |
| `backend/store.py` | Settings, models, indexed place key |
| `backend/catalog/` | Capability questions and license-source registry |
| `frontend/src/api/` | Query client and brief types |
| `frontend/src/chrome/` | Mark, search, thinking orb, rail |
| `frontend/src/graph/` | Workspace graph build, layout, canvas |
| `frontend/src/maps/` | Autocomplete and Street View |
| `tests/` | Checks nested by area (`fetch`, `brief`, `place`, `think`) |

One path: address → `fetch` → `place` → `brief` → Query cache → graph.

Add a city license as a JSON row in `backend/catalog/`. Uncovered trails
stay visible; we do not invent occupants.

## Local development

Copy `.env.example` to `.env` at the repo root. Set `VITE_GOOGLE_MAPS_API_KEY`
if you want Street View. Backend settings and Vite both read that file.

Graph copy on the workspace is fused through Vertex DeepSeek using Application
Default Credentials (`gcloud auth login --update-adc`). There is no DeepSeek
API key. Set `GRAPH_AI=false` to keep the deterministic graph only.

Two processes: API + Postgres via Docker Compose, and the Vite frontend.

### 1. Backend

```sh
make dev
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### 2. Frontend

```sh
make frontend
```

Open http://localhost:5173. Vite proxies `/location`, `/brief`, and `/health`
to the API.

### 3. Try an address

Use a full street address with city and state:

```text
501 O'Farrell St San Francisco CA 94102
```

Street-only inputs often fail geocoding.

## Checks

```sh
make test
make lint
```

## Design notes

Signals are the system of record. `source_watermarks` record the last
successful ingest per location and source. `brief_snapshots` are
materialized derived data, served when every source is still fresh.
Failed fetches leave previous facts in place.
