# Temporal

**Place intelligence from public records.** Type in an address and Temporal builds a brief — then a graph — of what licensed businesses, permits, and nearby incidents can actually say about that pin.

It is not a listing site, a credit score, or a people-search tool. If a trail is not wired for that city, the graph leaves the gap visible. It does not invent occupants, tenants, or contractors.

Live demo: [temporal-olive.vercel.app](https://temporal-olive.vercel.app)

## Objective

The goal of this repo is a **record-first** place workspace:

1. **Resolve a pin.** Geocode a full street address and store it.
2. **Pull only what is on file.** Business licenses, building permits, nearby crime counts — whatever sources are registered for that place.
3. **Open the questions that class of place can answer.** A commercial site asks who operated here; a house asks who lived here. Those questions live in `backend/catalog/`.
4. **Draw a DAG.** Place → trails → named entities, plus AI thoughts *between* existing nodes when something is worth saying.
5. **Stay honest.** AI may phrase a reading and splice a thought onto ids that already exist. It cannot add a person, firm, or edge that is not in the record graph.

Facts live in `signals`. Briefs are derived from those facts and snapshotted until a source goes stale. Opening an address does not scrape the world on every click.

## What you see

| Surface | What it is |
|---|---|
| Search | Address bar with optional Google Places autocomplete |
| Graph | Cards and routed edges: place, trails (answered / empty / unwired), entities, AI thoughts |
| Overview | The same brief as structured copy and source notes |

Try a full address with city and state:

```text
501 O'Farrell St San Francisco CA 94102
```

Street-only inputs often fail geocoding.

## How a brief is built

```text
address → /location (geocode) → /brief (refresh stale sources)
        → classify place → project entities/edges → open catalog trails
        → optional Vertex reading, grounded to existing ids
        → frontend workspace graph + layout
```

- **Fetch** talks to public APIs (Census, Socrata, optional permit portals, SFPD nearby crime).
- **Place** decides what is stale and writes signals.
- **Brief** classifies the site, builds the record graph, and fills modules from the catalog.
- **Think** asks Vertex DeepSeek for copy and thoughts, then drops unknown ids. If Vertex is off or fails, the same shapes are filled from local rules.
- **Graph UI** turns that brief into cards. Lines are laid out so they do not pass through other cards.

Add a city license source as a JSON row in `backend/catalog/`. Uncovered trails stay on the graph.

## Stack

- **API:** Python 3.11, FastAPI, SQLAlchemy (PostgreSQL locally, SQLite on the Hobby Vercel deploy)
- **UI:** TypeScript, React, Vite, TanStack Query, Tailwind
- **Ingest:** httpx against public APIs
- **Optional AI:** Vertex DeepSeek via Application Default Credentials (`gcloud auth login --update-adc`). There is no DeepSeek API key. Set `GRAPH_AI=false` for the deterministic graph only.

## Layout

| Path | Role |
|---|---|
| `backend/app.py` | HTTP door (`/location`, `/brief`, `/health`) |
| `backend/fetch/` | Geocode, licenses, permits, crime |
| `backend/place.py` | Identify a place, persist signals, staleness |
| `backend/brief/` | Classify, graph, modules, snapshot |
| `backend/think.py` | Vertex copy fused onto existing ids |
| `backend/store.py` | Settings, models, indexed place key |
| `backend/catalog/` | Capability questions and license-source registry |
| `frontend/src/api/` | Query client and brief types |
| `frontend/src/chrome/` | Mark, search, thinking field, rail |
| `frontend/src/graph/` | Workspace graph build, layout, canvas |
| `frontend/src/maps/` | Autocomplete and Street View |
| `tests/` | Checks nested by area (`fetch`, `brief`, `place`, `think`) |

## Local development

Copy `.env.example` to `.env` at the repo root. Set `VITE_GOOGLE_MAPS_API_KEY` if you want Street View and address autocomplete. Backend settings and Vite both read that file.

Two processes: API + Postgres via Docker Compose, and the Vite frontend.

```sh
make dev        # API at http://localhost:8000
make frontend   # UI at http://localhost:5173
```

Vite proxies `/location`, `/brief`, and `/health` to the API. Docs: http://localhost:8000/docs

```sh
make test
make lint
```

## Deploy

The Hobby demo is a single Vercel project: FastAPI serves the built UI. On Vercel the database is ephemeral SQLite (`/tmp`), so a cold start fetches public records again. Vertex is off there unless you attach GCP credentials.

```sh
vercel deploy --prod
```

`vercel.json` and `[tool.vercel]` in `pyproject.toml` point Vercel at `backend.app:app` and build the frontend first.

## Design notes

Signals are the system of record. `source_watermarks` record the last successful ingest per location and source. `brief_snapshots` are materialized derived data, served when every source is still fresh. Failed fetches leave previous facts in place.
