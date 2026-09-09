# Plan: Descaling warning (ticket 003)

## Goal

Machines need descaling regularly or the coffee gets worse and they break.
Add a warning when a machine needs descaling, so staff notice before it
becomes a quality/reliability problem — no such warning existed before.

## Scope

No descale-interval concept existed anywhere in the code. The sample
maintenance CSVs imply a real-world quarterly cadence: Bertha's two descale
events are 81 days apart, with the second one's note ("descale light had
been on for a week") admitting it was already overdue; The Intern's one
logged descale is also labeled "quarterly descale". Rocket and Old Faithful
each show only a single incidental descale (bundled with a repair/vendor
visit), not a scheduled one.

Decisions made:
- Warn when **90+ days have passed since a machine's last `type='descale'`
  maintenance event**, matching the implied quarterly cadence.
- A machine with **no descale on record at all** counts as needing one
  (maximally overdue — safest default).
- Delivered as a **simple per-card badge**, not folded into the ticket-001
  alerts panel — `get_alerts` is hardcoded to error-count fields
  (`error_count`, `last_error_at`, `error_code`) with no `kind`
  discriminator, so reusing that panel would need a real refactor; a badge
  ships the same visibility for much less change.
- The badge is plain language with no codes/notes, so unlike the gated
  `maintenanceAndErrors` block added in ticket 006, it stays visible in
  lobby mode too — it isn't the kind of internal jargon that ticket asked
  to hide.

## Backend changes

**`src/brewops/db/queries.py`**:

```python
DESCALE_WARNING_DAYS = 90

def get_machine_health(conn, machine_id, now=None) -> dict | None:
    ...
```

- `get_machine_health` gained an injectable `now` parameter (mirroring
  `get_alerts`'s test-only clock seam from ticket 001) and two new fields on
  its return dict: `last_descale` (the most recent `type='descale'` event's
  timestamp, or `None`) and `needs_descale` (`True` if none on record or the
  gap to `now` is `>= DESCALE_WARNING_DAYS`).
- Implemented as one more small query inside the existing function, matching
  its established pattern of several small single-purpose queries
  (`last_maintenance`, `recent_errors`, `specialty`, `busiest_day`) rather
  than introducing a new query function.

**`src/brewops/api/main.py`** — no changes; `GET /api/machines/{machine_id}`
already passes the dict straight through, so `last_descale`/`needs_descale`
appear in the JSON for free.

## Frontend changes

**`src/brewops/frontend/app.js`** — `renderMachineCards` renders a
`<p class="badge badge-warning">Needs descaling</p>` next to the existing
telemetry/manual-log badge when `m.needs_descale` is true. Placed
**unconditionally**, not gated by `LOBBY_MODE` like the maintenance/errors
block, per the scope decision above.

**`src/brewops/frontend/style.css`** — added `.badge-warning`, reusing the
`--warn`/`--warn-bg` variables already established for error styling in
ticket 001, so the descale badge reads as "needs attention" using the same
visual language as the rest of the app, distinct from the neutral brass
telemetry badge.

## Tests

**`tests/test_db.py`** — three new `get_machine_health` cases using the
injectable `now`: overdue (181-day gap → `needs_descale is True`), recent
(16-day gap → `False`), and never-descaled (`last_descale is None` →
`needs_descale is True`).

**`tests/test_api.py`** — extended the existing machine-health route test to
assert `last_descale` matches the fixture's seeded descale event and that
`needs_descale` is present in the response.

## Out of scope / explicitly not doing

- No refactor of the ticket-001 alerts panel to support multiple alert
  "kinds" — judged unnecessary complexity for what a card badge already
  solves.
- No brew-count-based descale trigger — no signal in the data supports one;
  time-since-last-descale was the only real-world cadence found.
- No new manual-entry UI changes — descale events are already loggable via
  the existing "Log maintenance" form (`type: descale`); this ticket only
  adds a computed warning from existing data.
