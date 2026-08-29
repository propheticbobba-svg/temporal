# Temporal

Place intelligence. Submit an address, get a structured brief of public
signals over time — permits, business licenses, and whatever sources you
register next.

Facts live in `signals`. Briefs are derived from those facts and stored
until the source is stale. The request path does not refetch the world
on every click.

## Stack

- Backend: Python 3.11, FastAPI, SQLAlchemy, PostgreSQL
- Frontend: TypeScript, React, Vite
- Ingestion: httpx against public APIs (Census, Socrata, optional permits)

## Layers

| Layer | Role |
|---|---|
| `ingestion/capabilities.json` | Questions we ask, which place classes they belong to, provider order |
| `ingestion/` | Fetch external data and write normalized signals (source of truth) |
| `jobs/` | Ingester registry and refresh intervals |
| `agent/place_class.py` | Weighted votes: assessor, licenses, address tokens, permits |
| `agent/graph.py` | Place → typed edges → entities, merged by normalized name |
| `agent/` | Derive a brief: classify, relate, then emit class-specific modules |
| `api/` | HTTP boundary: validate, orchestrate, return JSON |
| `frontend/` | TypeScript client |

Add a city license as a JSON row. Add a new kind of question in
`capabilities.json`. The brief UI opens only the capabilities for the
winning place class. Uncovered trails stay visible; we do not invent
occupants or gardeners.

## Local development

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
4600 Silver Hill Rd Washington DC 20233
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
