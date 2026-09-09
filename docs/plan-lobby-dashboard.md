# Plan: Reception screen — hide technical details from machine cards (ticket 006)

## Goal

Facilities is mounting a dashboard screen in reception so visitors see the
coffee fleet when they walk in. The machine cards show internal detail —
error codes like `E14`, descale notes — that means nothing to visitors and
clutters the cards on a public screen. Urgent: screen goes up Thursday
morning.

## Scope

The dashboard is a single shared page (`index.html`/`app.js`/`style.css`)
used both by staff internally and, as of this ticket, displayed publicly —
there was no existing staff/visitor distinction anywhere in the codebase.

The alerts panel added in ticket 001 also surfaces raw error codes (e.g.
"3 errors in the last 7 days (E13, E13, E13)") right at the top of the same
page — stripping the machine cards alone would still leave error codes
visible to visitors via that panel.

Chosen approach: a **lobby mode** toggled by a URL flag (`/?lobby=1`) that
the reception screen loads, rather than splitting into two separate
pages/routes or a build step. In lobby mode:

- machine cards drop the maintenance/error lines,
- the alerts panel stays hidden (never fetched),
- the "Log a brew" / "Log maintenance" forms are hidden — no data-entry
  tools belong on a public screen.

Staff keep the plain URL (`/`) with the full dashboard unchanged.

## Frontend changes

**`src/brewops/frontend/app.js`**:

```javascript
const LOBBY_MODE = new URLSearchParams(location.search).get("lobby") === "1";
if (LOBBY_MODE) document.body.classList.add("lobby-mode");
```

- `renderMachineCards` only builds the "Last maintenance"/"Recent errors"
  markup when `!LOBBY_MODE`; in lobby mode that block is omitted outright
  rather than rendered with placeholder text.
- Init sequence skips `setupForms()` and `loadAlerts()` (plus its 60s
  `setInterval` poll) entirely when `LOBBY_MODE` is set — no reason to fetch
  data or wire up forms nobody will use. `#alerts-panel` already defaults to
  `hidden` in the markup, so skipping the fetch is sufficient; no extra CSS
  needed for it.

**`src/brewops/frontend/style.css`**:

```css
body.lobby-mode .form-panel {
  display: none;
}
```

Reuses the existing shared `.form-panel` class already on both the
brew-log and maintenance-log sections — no HTML changes needed.

**`src/brewops/frontend/index.html`** — no changes required.

## Tests

**`tests/test_frontend.py`** — added a smoke test asserting the served
`/app.js` contains `LOBBY_MODE` and `/style.css` contains `lobby-mode`,
mirroring the existing string-membership style of this test file (there's
no headless JS execution/browser test runner in this repo, so genuine
behavioral verification — does `?lobby=1` actually hide the right things —
has to happen by eye in a browser).

## Out of scope / explicitly not doing

- No new route/page/build step — same static bundle, branched client-side
  on a query param.
- No backend/API changes — `/api/machines/{id}` still returns
  `last_maintenance`/`recent_errors` in its JSON; only lobby-mode rendering
  suppresses it, so other consumers (CSV export, future features) are
  unaffected.
- Date filter (`.date-filter`) stays visible in lobby mode — not mentioned
  in the ticket, and it's a read-only control rather than a data-entry tool.
