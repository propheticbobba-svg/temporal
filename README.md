# Temporal Project

A data-first place intelligence platform. Given an address, the API returns a
structured brief describing what has been happening at that location over time.

## Layers

- `ingestion/`: fetches external source data and writes normalized signals.
- `agent/`: reads stored signals and produces a structured brief.
- `api/`: validates requests, calls the agent, and returns responses.

New signal sources should only add an ingester, register it in `jobs/scheduler.py`,
and add ingestion tests.

## Local Development Tutorial

This project has two local processes:

- FastAPI backend plus Postgres and Redis through Docker Compose.
- Vite React frontend from `frontend/`.

### Prerequisites

- Docker Desktop running.
- Node.js and npm installed.
- Python virtualenv installed if you plan to run tests or lint locally.

### 1. Start the backend stack

From the repository root:

```sh
cd /Users/kesav_bobba/Documents/temporal-proj
make dev
```

Leave this terminal open. It starts:

- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

The API creates the local database tables on startup. Docker Compose waits for
Postgres to be healthy before starting the API.

### 2. Start the frontend

Open a second terminal:

```sh
cd /Users/kesav_bobba/Documents/temporal-proj
npm install --prefix frontend
npm --prefix frontend run dev
```

Open the app:

```text
http://localhost:5173
```

The frontend uses Vite's dev proxy to forward `/location` and `/brief` to the
backend on `http://localhost:8000`.

### 3. Try a location

Use a full address with city and state:

```text
949 Abbott Lane, Allen, TX
```

Short street-only inputs such as `949 Abbott Lane` may fail because the geocoder
does not have enough locality context to choose the correct address.

### Verification Commands

Check the backend directly:

```sh
curl -i -X POST http://localhost:8000/location \
  -H 'Content-Type: application/json' \
  -d '{"address":"949 Abbott Lane, Allen, TX"}'
```

Check the frontend proxy:

```sh
curl -i -X POST http://localhost:5173/location \
  -H 'Content-Type: application/json' \
  -d '{"address":"949 Abbott Lane, Allen, TX"}'
```

Run automated checks:

```sh
make test
make lint
npm --prefix frontend run build
```

### Troubleshooting

If `make dev` says it cannot connect to Docker, start Docker Desktop and run the
command again.

If `make dev` fails because port `5432` is already in use, another local
Postgres process is running. Stop that process or change the Compose port
mapping before starting the stack.

If the frontend shows `Request failed with status 502`, the Vite dev server is
running but the API is not reachable on `localhost:8000`. Check that the backend
terminal is still running and that `http://localhost:8000/docs` loads.

If the browser says `ERR_CONNECTION_REFUSED` for `localhost:5173`, the Vite
frontend server is not running. Start it with:

```sh
npm --prefix frontend run dev
```

If geocoding returns `422`, try a more complete address with city, state, and
ZIP code.
