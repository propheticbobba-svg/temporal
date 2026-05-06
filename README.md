# Temporal Project

A data-first place intelligence platform. Given an address, the API returns a
structured brief describing what has been happening at that location over time.

## Layers

- `ingestion/`: fetches external source data and writes normalized signals.
- `agent/`: reads stored signals and produces a structured brief.
- `api/`: validates requests, calls the agent, and returns responses.

New signal sources should only add an ingester, register it in `jobs/scheduler.py`,
and add ingestion tests.
