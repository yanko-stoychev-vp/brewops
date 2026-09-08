# BrewOps

Telemetry and ops app for the office coffee machines. Python (FastAPI) + SQLite, no ORM.

## Architecture

`data/inbox/*.csv` → **ingest** (`src/brewops/ingest/`) → **db** (`src/brewops/db/`, SQLite) → **api** (`src/brewops/api/main.py`, FastAPI) → **frontend** (`src/brewops/frontend/`, vanilla JS, served by the same process).

- `db/schema.py` — table definitions + seed reference data (`machines`, `drink_types`); `db/connection.py` opens the sqlite3 connection (`row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`); `db/queries.py` holds every read/write query.
- `api/main.py` runs one process serving both the JSON API under `/api/*` and the static frontend mounted at `/`. GET endpoints return DB-layer dicts straight through as JSON — no Pydantic response models. POST endpoints (`/api/brews`, `/api/maintenance`) validate with Pydantic request models (`BrewIn`, `MaintenanceIn`).
- `frontend/app.js` — no build step, no framework; fetches `/api/*` and renders DOM directly.

## Two ingestion paths

1. **CSV batch** — `uv run ingest [path]` (default `data/inbox/`), or `uv run seed` to reset the DB and reload everything. Routing is by filename prefix (`ingest/loader.py`): `brews_*.csv` → brew events with `source="csv"`; `manual_*.csv` → brew events with `source="manual"` (Old Faithful's paper log, the one machine with `has_telemetry=False`); `maintenance_*.csv` → maintenance events. Bad rows are skipped and reported, not fatal to the file.
2. **Manual entry** — the frontend's forms POST to `/api/brews` / `/api/maintenance`, which always insert with `source="manual"`.

## Running and testing

- `uv run start` — serves the app at http://localhost:8123 (creates/uses `./brewops.db`, or `$BREWOPS_DB` if set).
- `uv run seed` — wipes and repopulates the DB from `data/inbox/`. Run this once before first use.
- `uv run pytest` — unit + API tests in `tests/`. No `httpx` dependency by design; `tests/asgi_client.py` is a minimal stdlib-only ASGI client used instead of Starlette's `TestClient`. API tests isolate the DB via `tmp_path` + `monkeypatch.setenv("BREWOPS_DB", ...)`.
- `scripts/lab_a_check.py` — standalone verification script for the machine-specialty feature; auto-starts the app if not already running. On Windows, its subprocess cleanup can leave an orphaned `python.exe` listening on 8123 if the app was already mid-restart — check `Get-NetTCPConnection -LocalPort 8123` if a check result looks stale.

## Conventions

- Timestamps are naive local time, stored and compared as `'YYYY-MM-DD HH:MM:SS'` strings — no timezone handling anywhere.
- Query functions return plain `dict`/`list[dict]`, often built with `dict(row) | {...}` to merge in derived fields; no dataclasses/ORM models on the read path.
- SQL lives inline in `queries.py` as triple-quoted strings, one function per logical query — mirror this pattern rather than adding a query builder.
- Drink types are a reference table (`drink_types`); brew events store the machine-readable `name` (e.g. `espresso`), and callers join to `drink_types` for the display `label` (e.g. `Espresso`) when needed.
