# Plan: CSV export for finance (ticket 002)

## Goal

Finance currently screenshots the dashboard once a month. Give them a
"Download CSV" button that exports brew data (with machine/drink names
resolved, not just IDs) for the currently selected date range, so it opens
cleanly in Excel.

## Scope

Export raw brew events, not pre-aggregated stats — finance wants numbers
they can pivot themselves, and this reuses the existing `date_from`/`date_to`
filtering already on the dashboard (added in ticket 005). Maintenance events
are out of scope; nothing in the ticket asks for them, and can be added later
as a separate endpoint if requested.

## Backend changes

**`src/brewops/db/queries.py`** — add `get_brews_for_export`:

```python
def get_brews_for_export(conn, date_from=None, date_to=None) -> list[dict]:
    """Brew events joined with machine/drink labels, for CSV export."""
```

- Mirrors the `WHERE`/params construction already in `get_stats` (same
  inclusive `date_from`/`date_to` semantics, so the export always matches
  what's on screen).
- `SELECT be.timestamp, m.name AS machine, dt.label AS drink, be.duration_s,
  be.temp_c, be.source FROM brew_events be JOIN machines m ON m.id =
  be.machine_id JOIN drink_types dt ON dt.name = be.drink_type {where} ORDER
  BY be.timestamp`.

**`src/brewops/api/main.py`** — add `GET /api/export/brews.csv`:

- Reuse the same `date_from`/`date_to` validation block currently duplicated
  in `stats()` (pull it into a small `validate_date_range` helper used by
  both endpoints, since we'd otherwise have three copies once this lands).
- Build the CSV with the stdlib `csv` module into a `io.StringIO`, header
  row `timestamp, machine, drink, duration_s, temp_c, source`.
- Return via `fastapi.responses.Response` with
  `media_type="text/csv"` and
  `Content-Disposition: attachment; filename="brewops-brews.csv"` (or a
  filename that includes the date range if one was given, e.g.
  `brewops-brews-2026-01-01_2026-03-31.csv`) so the browser downloads rather
  than navigates.
- No pagination/streaming needed at this data volume (office coffee
  machines, not a firehose) — build the whole CSV in memory like the
  existing GET endpoints build their whole JSON response.

## Frontend changes

**`src/brewops/frontend/index.html` / `app.js`** — add a "Download CSV" link
next to the existing date-range filter inputs (`filter-from`/`filter-to`).

- Plain `<a>` tag, not a fetch — CSV download is a browser navigation, not
  an API call the JS needs to read.
- `href` built the same way `loadDashboard()` builds the stats query string:
  reuse the `date_from`/`date_to` params from the two filter inputs so the
  download always matches whatever range is currently shown.
- Simplest approach: give the link a fixed base href and update its
  `href` attribute inside `loadDashboard()` (same place the params are
  already assembled), rather than adding a second click handler.

## Tests

**`tests/`** — add an API test alongside the existing `/api/stats` tests:

- Hits `/api/export/brews.csv`, asserts `content-type` is `text/csv` and the
  `Content-Disposition` header is present.
- Parses the body with `csv.reader` and checks the header row and one known
  seeded row.
- Repeats with `date_from`/`date_to` set and confirms filtered rows match
  `get_stats`'s `total_brews` count for the same range (cheap way to catch a
  filter-logic mismatch between the two endpoints).
- Invalid date range (`date_from` after `date_to`) returns 400, same as
  `/api/stats`.

## Out of scope / explicitly not doing

- No maintenance-event export (not requested).
- No XLSX generation — CSV opens fine in Excel and avoids adding a new
  dependency for formatting Excel wants (finance can format columns
  themselves).
- No async/streaming response — data volume doesn't warrant it.
