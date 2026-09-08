# Implementation plan: dashboard date-range filter (ticket 005)

## Context

The dashboard (`/`, served by `src/brewops/api/main.py`, rendered by `src/brewops/frontend/`) currently shows all-time totals with no way to narrow the view to a specific period. `tickets/005-date-filter.md` asks for a date-range picker so the stat tiles, drink breakdown, and daily timeline chart can answer "was last week normal?" instead of only "what's the grand total?".

**Decisions made for this plan (no further sign-off needed):**
- **Scope**: only the main dashboard stats (`GET /api/stats` → stat tiles, drink bars, timeline). The per-machine health cards (`GET /api/machines/{id}`, `get_machine_health`) stay all-time and are NOT touched by this change — they are a separate per-machine detail view, not the aggregate dashboard the ticket complains about.
- **Default behavior**: if no range is given, `/api/stats` returns all-time data, exactly like today. The filter is purely additive — nothing breaks if a caller omits the new params.
- **Param format**: plain date strings `YYYY-MM-DD` (not full datetime). This matches how a user picks a range (whole days), and the stored timestamp format `YYYY-MM-DD HH:MM:SS` sorts lexically, so date-only bounds compare correctly.

## Files and functions to change

### 1. `src/brewops/db/queries.py` — `get_stats` (currently lines 68-94)

Change the signature from `get_stats(conn)` to `get_stats(conn, date_from: str | None = None, date_to: str | None = None)`.

Both params are optional and are plain `'YYYY-MM-DD'` strings, or `None` for "no bound on that side".

For each of the three sub-queries, add a WHERE clause built conditionally:
- If `date_from` is given, require `timestamp >= date_from` (a bare date like `'2026-06-01'` string-compares correctly against `'2026-06-01 00:00:00'`-style timestamps because it's a shorter, purely alphabetic prefix — SQLite compares strings lexically, and `'2026-06-01' <= '2026-06-01 07:00:00'` is true).
- If `date_to` is given, require `timestamp < date_to || ' 23:59:59'` conceptually — in practice, append `' 23:59:59'` to `date_to` in Python before passing it into the query so the bound is inclusive of the whole end day: `timestamp <= date_to_with_time`.

Concretely, build the WHERE clause and params list once at the top of the function and reuse it in all three queries:

```python
def get_stats(conn, date_from=None, date_to=None):
    clauses = []
    params = []
    if date_from:
        clauses.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("timestamp <= ?")
        params.append(f"{date_to} 23:59:59")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
```

Then:
- **total** query becomes `SELECT COUNT(*) AS n FROM brew_events {where}` with `params`.
- **per_drink** query: the existing query LEFT JOINs from `drink_types` to `brew_events` so that drinks with zero brews still appear with `count=0`. The date filter must go in the `ON` clause, not a `WHERE`, otherwise the LEFT JOIN semantics break and out-of-range drinks would disappear entirely instead of showing 0:
  ```sql
  SELECT dt.name, dt.label, COUNT(be.id) AS count
  FROM drink_types dt
  LEFT JOIN brew_events be ON be.drink_type = dt.name {AND-version-of-where}
  GROUP BY dt.id
  ORDER BY dt.id
  ```
  i.e. reuse the same clause list but joined with `AND` and prefixed with `AND` (not `WHERE`), appended to the `ON` condition. Build a second string for this case, e.g. `on_extra = (" AND " + " AND ".join(clauses)) if clauses else ""`.
- **per_day** query becomes `SELECT DATE(timestamp) AS day, COUNT(*) AS count FROM brew_events {where} GROUP BY DATE(timestamp) ORDER BY day` with `params`. This naturally returns **no rows for days with zero brews** — the frontend already handles a sparse `per_day` list (see step 3), so no change needed there for "days with no brews": they simply don't appear as entries, they don't appear as zero-filled gaps.

Do not touch `get_machine_health` (lines 97-160) — out of scope per the decision above.

### 2. `src/brewops/api/main.py` — `stats` endpoint (currently lines 73-75)

Add two optional query params, `from_` and `to` is awkward because `from` is a Python keyword — use `date_from` and `date_to` as the query param names directly (FastAPI allows this, no keyword clash since they're not Python identifiers in the URL, only in the function signature where they're already valid names):

```python
@app.get("/api/stats")
def stats(
    date_from: str | None = None,
    date_to: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    return queries.get_stats(conn, date_from, date_to)
```

Notes:
- String comparison `date_from > date_to` works directly on `'YYYY-MM-DD'` strings — no need to parse into `datetime` objects, consistent with how the rest of the codebase treats these strings as sortable text (see `DATE(timestamp)` usage in queries.py).
- Do **not** reuse `parse_timestamp()` (lines 41-54) — that function is for full datetime strings coming from POST bodies (brew/maintenance forms) and enforces "not in the future," which doesn't apply to filter bounds. Keep this validation separate and minimal: just the `date_from > date_to` check.
- `HTTPException` is already imported in this file (used elsewhere for the 404 on unknown machine, line ~86) — confirm the import exists before using it; if not, add `from fastapi import HTTPException` alongside the existing FastAPI imports at the top of the file.
- No changes needed to `POST /api/brews` or `POST /api/maintenance`.

### 3. `src/brewops/frontend/index.html`

Add a small filter control directly above the `.stat-tiles` div inside `#dashboard` (currently starting around line 17). Two native date inputs plus a clear button, no library needed:

```html
<div class="date-filter">
  <label>From <input type="date" id="filter-from"></label>
  <label>To <input type="date" id="filter-to"></label>
  <button id="filter-clear" type="button">Clear</button>
</div>
```

Keep it simple — no "Apply" button; the inputs trigger `loadDashboard()` on `change` (see step 4). This matches the app's existing style of immediate, no-submit-button interactions (compare to how forms currently work, but note brew/maintenance forms are the only "submit" flows in the app — the filter is a live view control, not a form to submit).

### 4. `src/brewops/frontend/app.js`

Current flow: `loadDashboard()` (lines 84-96) takes no arguments and calls `fetchJSON("/api/stats")` unconditionally (line 85).

Changes:
- At the top of the file (near other DOM references, e.g. where `#total-brews` etc. are looked up), grab the new inputs: `const filterFrom = document.getElementById("filter-from");`, `const filterTo = document.getElementById("filter-to");`, `const filterClear = document.getElementById("filter-clear");`.
- Modify `loadDashboard()` to build the query string from current input values:
  ```js
  async function loadDashboard() {
    const params = new URLSearchParams();
    if (filterFrom.value) params.set("date_from", filterFrom.value);
    if (filterTo.value) params.set("date_to", filterTo.value);
    const qs = params.toString();
    const stats = await fetchJSON(`/api/stats${qs ? "?" + qs : ""}`);
    ...
  }
  ```
  The rest of the function (stat tiles, `renderDrinkBars`, `renderTimeline`, machine cards fetch) stays as-is.
- Add event listeners near the bottom of the file, alongside the existing `loadDashboard()` call at script load (currently line 163):
  ```js
  filterFrom.addEventListener("change", loadDashboard);
  filterTo.addEventListener("change", loadDashboard);
  filterClear.addEventListener("click", () => {
    filterFrom.value = "";
    filterTo.value = "";
    loadDashboard();
  });
  ```
- **"Brews today" tile** (line 87, currently `stats.per_day[stats.per_day.length - 1]`): when a range is active, the last entry in `per_day` is the last day *in the filtered range*, not necessarily today. Change the label dynamically: if both `filterFrom` and `filterTo` are empty (all-time / today included), keep the existing "brews on last active day" wording; if a range is active, relabel the tile (e.g. to "Brews on last day in range") so it doesn't imply "today" when it isn't. The simplest implementation: always use the existing per-day-tail logic for the *value*, but swap the tile's label text based on whether a filter is active. Locate the tile's label element in `index.html` (near `#brews-today`, around line 25) and give it an `id` so `app.js` can update its text, e.g. `document.getElementById("brews-today-label").textContent = qs ? "Brews on last day in range" : "Brews on last active day";`.

### 5. `src/brewops/frontend/style.css`

Add minimal styling for `.date-filter` (flex row, gap, aligned with existing `.panel`/`.stat-tiles` spacing conventions already in the file — match existing margin/gap values used by `.stat-tiles`, don't invent new spacing units).

## Edge cases and how each is handled

| Case | Behavior |
|---|---|
| No range selected (both inputs empty) | `date_from`/`date_to` omitted from query string entirely → `get_stats(conn, None, None)` → no WHERE clause → all-time results, identical to current behavior. |
| Only `date_from` set | Only the `timestamp >= date_from` bound applies; results include everything from that date to the latest brew. |
| Only `date_to` set | Only the `timestamp <= date_to 23:59:59` bound applies; results include everything up to and including that day. |
| `date_from` after `date_to` | API returns `400 Bad Request` with a clear message, before touching the DB. Verify: `GET /api/stats?date_from=2026-06-10&date_to=2026-06-01` → 400. |
| Empty range (valid dates, but zero brews fall inside them) | Not an error. `total_brews` is `0`, `per_drink` still lists every drink type with `count: 0` (LEFT JOIN preserves the reference rows), `per_day` is an empty list `[]`. Frontend must not crash on an empty `per_day` — check `renderTimeline`/`renderDrinkBars` (lines 14-50) already guard with `Math.max(1, ...)` so a render with all-zero/empty input should degrade to an empty or flat chart rather than throwing; confirm this manually (see verification below). |
| Days with no brews inside an otherwise non-empty range | Those days simply don't appear as rows in `per_day` — there is no zero-fill. This is existing behavior (unchanged from today), not a new edge case introduced by this feature; the timeline chart's bar width is `600 / perDay.length` (app.js ~line 45), so gaps are only visible as sparser bars, not zero-height bars on the missing date. Do not implement zero-filling — out of scope, it's the same behavior as the current all-time view has for machines with sporadic use. |
| Malformed date string (e.g. `date_from=not-a-date`) | Since the query is a plain string comparison, SQLite will not error, but the comparison result is meaningless (undefined ordering against real timestamps). Add a lightweight format check in the `stats` endpoint before calling `get_stats`: reject with `400` if either param doesn't match `YYYY-MM-DD` (e.g. `datetime.strptime(date_from, "%Y-%m-%d")` in a `try/except ValueError → HTTPException(400)`). |
| Range covering exactly one day (`date_from == date_to`) | Valid, not an error (equal is not "after"). Returns just that day's data. |
| Filter cleared after being set | `filter-clear` button resets both inputs and calls `loadDashboard()`, returning to all-time view. |

## Tests to update/add

- `tests/test_db.py::test_stats_math` (currently calls `get_stats(conn)` with no args) — add new cases calling `get_stats(conn, date_from=..., date_to=...)` using the fixture's known seeded dates (the `db` fixture seeds `2026-06-01`..`2026-06-03`), asserting narrower `total_brews`/`per_day` when the range excludes some seeded rows.
- `tests/test_db.py::test_reset_db_clears_events` — no change needed, still calls `get_stats(conn)` with no args, still expected to work since params are optional.
- `tests/test_api.py::test_stats` — add cases: `GET /api/stats?date_from=...&date_to=...` narrows results; `GET /api/stats` with no params still returns all-time (regression check); `GET /api/stats?date_from=2026-06-10&date_to=2026-06-01` returns 400.
- `tests/test_api.py::test_post_brew_ok_and_visible_in_stats` — no change needed (uses default all-time stats call).
- Add a new test for the empty-range case: pick a valid date range with no seeded brews in it, assert `total_brews == 0`, `per_drink` entries all have `count: 0`, `per_day == []`.

## Verification steps

1. Run `uv run pytest` — all existing and new tests pass.
2. Run `uv run seed` to repopulate `./brewops.db` from `data/inbox/`.
3. Run `uv run start`, open `http://localhost:8123`.
4. On page load, confirm dashboard shows the same all-time numbers as before this change (no regression).
5. Manually hit the API to sanity-check the new params before trusting the UI:
   - `curl http://localhost:8123/api/stats` — matches all-time baseline.
   - `curl "http://localhost:8123/api/stats?date_from=2026-06-01&date_to=2026-06-01"` — narrower, single-day totals.
   - `curl "http://localhost:8123/api/stats?date_from=2026-06-10&date_to=2026-06-01"` — expect `400`.
   - `curl "http://localhost:8123/api/stats?date_from=1900-01-01&date_to=1900-01-02"` — expect `total_brews: 0`, `per_day: []`, `per_drink` listing every drink type at `count: 0`.
6. In the browser, set the "From"/"To" date inputs to a narrow range covering only part of the seeded data; confirm the stat tiles, drink bars, and timeline chart all shrink to match, and the "brews today" tile's label changes to reflect that a range is active.
7. Click "Clear" and confirm the dashboard returns to the all-time view.
8. Confirm machine health cards (`#machine-cards`) are unaffected by the filter (out of scope) — they should show the same all-time numbers regardless of the date-range inputs.
