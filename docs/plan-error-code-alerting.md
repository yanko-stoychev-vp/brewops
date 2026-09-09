# Plan: Error-code alerting (ticket 001)

## Goal

Machine error codes were logged in maintenance history but nobody looked at
them until a machine actually died — the 4th-floor machine (Rocket) had been
throwing the same error for weeks. Surface repeated errors proactively so
staff can get the vendor in before an outage.

## Scope

No email/Slack/push infrastructure exists in this app — it's a single
FastAPI process serving REST + a vanilla-JS dashboard with no polling loop.
Given that, alerting is **in-app only**: a new endpoint that flags machines
with repeated errors, surfaced as a dashboard panel that refreshes on a
timer. Trigger is count-based, not severity-based, since `error_code` is
free-text (`"E13"`, `"E42"`, ...) with no ranking concept anywhere in the
data: a machine alerts when it has **2 or more `type='error'` maintenance
events within a trailing 7-day window**.

## Backend changes

**`src/brewops/db/schema.py`** — added a composite index,
`idx_maintenance_events_machine_type_ts` on
`maintenance_events(machine_id, type, timestamp)`, matching the new query's
access pattern (cheap to add via the existing `CREATE INDEX IF NOT EXISTS`
block, not load-bearing at this app's scale).

**`src/brewops/db/queries.py`** — added `get_alerts`:

```python
ALERT_MIN_ERRORS = 2
ALERT_WINDOW_DAYS = 7

def get_alerts(conn, min_errors=ALERT_MIN_ERRORS, window_days=ALERT_WINDOW_DAYS, now=None) -> list[dict]:
    """Machines with min_errors or more type='error' events in the trailing window_days."""
```

- Threshold/window as module constants (not a config system) — greppable
  and testable, no new infrastructure.
- Window boundary computed in Python (`datetime.now() - timedelta`),
  formatted to the same `'YYYY-MM-DD HH:MM:SS'` string used everywhere else.
- Fleet-wide aggregate query (`GROUP BY machine_id HAVING COUNT >= ?`)
  followed by a per-machine detail query for the qualifying events, mirroring
  `get_machine_health`'s style of several small queries.
- `now` is an injectable clock — a test-only seam, not exposed via the API.

**`src/brewops/api/main.py`** — added `GET /api/alerts`:

- Optional `min_errors`/`window_days` query params falling back to the
  module defaults, mirroring how `date_from`/`date_to` are optional on
  `/api/stats`.
- Plain list passthrough, no Pydantic response model, matching every other
  GET endpoint. Empty list (not 404) when the fleet is healthy.

## Frontend changes

**`src/brewops/frontend/index.html`** — new `#alerts-panel` section (starts
`hidden`), placed above the stat tiles so it reads as the most prominent
thing on load.

**`src/brewops/frontend/app.js`** — `renderAlerts`/`loadAlerts`:

- `renderAlerts` builds one `.alert-item` per machine in alert state,
  showing error count, window, the raw error codes, and last-seen timestamp.
  Un-hides the panel only when there's at least one alert.
- `loadAlerts` is called on init and polled every 60s via `setInterval`,
  kept independent from `loadDashboard()`'s date-filter-triggered reloads —
  alerts aren't affected by the date filter, and an alerts-fetch failure
  shouldn't fail the rest of the dashboard.

**`src/brewops/frontend/style.css`** — new `.alerts-panel`/`.alerts-list`/
`.alert-item`/`.alert-title` rules, reusing the existing `--warn`/`--warn-bg`
variables and the left-border-stripe idiom already used for error-flagged
machine cards.

A latent layout issue surfaced while wiring this in: `.stat-tiles` and the
other dashboard panels had fully-explicit `grid-row` values that left no row
for auto-placed full-width items (like the pre-existing `.date-filter`) to
land in — per the CSS Grid spec they'd get pushed to an implicit row below
everything. Fixed by giving `.date-filter` and `.alerts-panel` explicit rows
(1, 2) and shifting the other panels down (3, 4, 4, 5) so DOM order matches
visual order.

## Tests

**`tests/test_db.py`** — three `get_alerts` unit tests: repeated-error
machine flags correctly (mirrors the real `maintenance_2026-07.csv`
machine-4/E13 pattern), an error outside the trailing window doesn't count,
and a healthy fleet returns an empty list.

**`tests/test_api.py`** — one route test hitting `/api/alerts`, empty by
default, non-empty after seeding two errors for one machine.

## Out of scope / explicitly not doing

- No email/Slack/push notifications — no infra for it, and an in-app panel
  matches how the rest of this app already works (staff have the dashboard
  open).
- No severity/escalation ranking of `error_code` values — the data doesn't
  support it; count-based trigger was judged sufficient for the reported
  scenario.
- No manual-entry `error_code` field added to the "Log maintenance" form —
  out of scope for this ticket; error codes still enter via CSV ingest, and
  the alert still counts `type='error'` rows even without a code.
