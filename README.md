# Temporal

Type in an address. Temporal shows what public records can actually say about that place — over time.

Not a listing site, a credit score, or a people search. If a city is not wired, the gap stays on the graph. Nothing is invented.

**Why “Temporal”:** a pin is not a snapshot. Licenses, permits, and nearby incidents have dates. The product is that history — who operated here, what was permitted, what happened nearby — not a static listing.

Live demo: [temporal-buddies5.vercel.app](https://temporal-buddies5.vercel.app/)

## What it does

1. Geocode a full street address.
2. Pull only registered public sources (licenses, permits, nearby crime).
3. Open the questions that class of place can answer (a shop asks who operated here; a house asks who lived here).
4. Draw a graph: place → trails → named entities. Optional AI may phrase a reading on ids that already exist.

Try `501 O'Farrell St San Francisco CA 94102`. Street-only inputs often fail geocoding.

## Run locally

Copy `.env.example` to `.env`. Fill only what you need. Never commit `.env`.

Set `VITE_GOOGLE_MAPS_API_KEY` for Street View and autocomplete, and restrict that key to your hosts.

```sh
make dev        # API at http://localhost:8000
make frontend   # UI at http://localhost:5173
make test
```

Vite proxies `/location`, `/brief`, and `/health` to the API.

## Stack

Python 3.11 / FastAPI + React / Vite. Postgres locally, SQLite on the Hobby Vercel deploy. Optional Vertex fusion stays off unless `GRAPH_AI=true` and `VERTEX_PROJECT` are set (ADC, no model API key).

Sources live as JSON rows in `backend/catalog/`. Uncovered trails stay visible.

## Deploy

One Vercel project: FastAPI serves the built UI. The Hobby database is ephemeral SQLite (`/tmp`), so a cold start fetches public records again.

```sh
vercel deploy --prod
```

## Secrets

Nothing in this tree is a live credential. Keys, tokens, and cloud project ids belong in the environment, not in source.
