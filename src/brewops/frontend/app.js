// BrewOps frontend — vanilla JS, no dependencies, no build step.

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

const LOBBY_MODE = new URLSearchParams(location.search).get("lobby") === "1";
if (LOBBY_MODE) document.body.classList.add("lobby-mode");

// ---- dashboard ----

function renderDrinkBars(perDrink) {
  const container = document.getElementById("drink-bars");
  container.innerHTML = "";
  const max = Math.max(1, ...perDrink.map((d) => d.count));
  for (const drink of perDrink) {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="bar-label">${drink.label}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(drink.count / max) * 100}%"></span></span>
      <span class="bar-count">${drink.count}</span>`;
    container.appendChild(row);
  }
}

function renderTimeline(perDay) {
  const svg = document.getElementById("timeline");
  svg.innerHTML = "";
  if (perDay.length === 0) return;
  const width = 600;
  const height = 130;
  const max = Math.max(...perDay.map((d) => d.count));
  const barWidth = width / perDay.length;
  perDay.forEach((day, i) => {
    const barHeight = (day.count / max) * (height - 10);
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", i * barWidth);
    rect.setAttribute("y", height - barHeight);
    rect.setAttribute("width", Math.max(0.5, barWidth - 0.6));
    rect.setAttribute("height", barHeight);
    rect.setAttribute("class", "timeline-bar");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${day.day}: ${day.count} brews`;
    rect.appendChild(title);
    svg.appendChild(rect);
  });
}

function renderMachineCards(healths) {
  const container = document.getElementById("machine-cards");
  container.innerHTML = "";
  for (const m of healths) {
    const card = document.createElement("div");
    card.className = "card";
    const specialty = m.specialty
      ? `${m.specialty.label} (${m.specialty.count} total brews)`
      : "no brews yet";
    const busiestDay = m.busiest_day
      ? `${m.busiest_day.day} (${m.busiest_day.count} brews)`
      : "no brews yet";
    let maintenanceAndErrors = "";
    if (!LOBBY_MODE) {
      const maintenance = m.last_maintenance
        ? `${m.last_maintenance.type} on ${m.last_maintenance.timestamp.slice(0, 10)}`
        : "none on record";
      const errors = m.recent_errors.length
        ? `<p class="errors">Recent errors: ${m.recent_errors
            .map((e) => `${e.error_code || "?"} (${e.timestamp.slice(0, 10)})`)
            .join(", ")}</p>`
        : "";
      maintenanceAndErrors = `<p>Last maintenance: ${maintenance}</p>${errors}`;
    }
    const descaleBadge = m.needs_descale
      ? `<p class="badge badge-warning">Needs descaling</p>`
      : "";
    card.innerHTML = `
      <h3>${m.name}</h3>
      <p class="badge">${m.has_telemetry ? "telemetry" : "manual log"}</p>
      ${descaleBadge}
      <p>${m.brew_count} brews · last ${m.last_brew ? m.last_brew.slice(0, 16) : "never"}</p>
      <p>Specialty: ${specialty}</p>
      <p>Busiest day: ${busiestDay}</p>
      ${maintenanceAndErrors}`;
    container.appendChild(card);
  }
}

function renderAlerts(alerts) {
  const panel = document.getElementById("alerts-panel");
  const container = document.getElementById("alerts-list");
  container.innerHTML = "";
  panel.hidden = alerts.length === 0;
  if (alerts.length === 0) return;
  for (const a of alerts) {
    const item = document.createElement("div");
    item.className = "alert-item";
    const codes = a.events.map((e) => e.error_code || "?").join(", ");
    item.innerHTML = `
      <p class="alert-title">${a.name}</p>
      <p>${a.error_count} errors in the last ${a.window_days} days (${codes}) — last at ${a.last_error_at.slice(0, 16)}</p>`;
    container.appendChild(item);
  }
}

async function loadAlerts() {
  const alerts = await fetchJSON("/api/alerts");
  renderAlerts(alerts);
}

async function loadDashboard() {
  const filterFrom = document.getElementById("filter-from");
  const filterTo = document.getElementById("filter-to");
  const params = new URLSearchParams();
  if (filterFrom.value) params.set("date_from", filterFrom.value);
  if (filterTo.value) params.set("date_to", filterTo.value);
  const qs = params.toString();
  const stats = await fetchJSON(`/api/stats${qs ? "?" + qs : ""}`);

  document.getElementById("total-brews").textContent = stats.total_brews;
  const lastDay = stats.per_day[stats.per_day.length - 1];
  document.getElementById("brews-today").textContent = lastDay ? lastDay.count : 0;

  const isFiltered = filterFrom.value || filterTo.value;
  const label = document.getElementById("brews-today-label");
  label.textContent = isFiltered ? "brews on last day in range" : "brews on last active day";

  // Update CSV download link with current filters
  const csvLink = document.getElementById("csv-download");
  csvLink.href = `/api/export/brews.csv${qs ? "?" + qs : ""}`;

  renderDrinkBars(stats.per_drink);
  renderTimeline(stats.per_day);

  const machines = await fetchJSON("/api/machines");
  document.getElementById("machine-count").textContent = machines.length;
  const healths = await Promise.all(machines.map((m) => fetchJSON(`/api/machines/${m.id}`)));
  renderMachineCards(healths);
}

// ---- forms ----

function localNow() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16); // datetime-local format
}

function fillSelect(select, items, valueKey, labelKey) {
  select.innerHTML = "";
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item[valueKey];
    option.textContent = item[labelKey];
    select.appendChild(option);
  }
}

async function setupForms() {
  const machines = await fetchJSON("/api/machines");
  const drinks = await fetchJSON("/api/drink-types");
  fillSelect(document.getElementById("brew-machine"), machines, "id", "name");
  fillSelect(document.getElementById("brew-drink"), drinks, "name", "label");
  fillSelect(document.getElementById("maintenance-machine"), machines, "id", "name");
  document.getElementById("brew-timestamp").value = localNow();
  document.getElementById("maintenance-timestamp").value = localNow();

  document.getElementById("brew-form").addEventListener("submit", (event) =>
    submitForm(event, "/api/brews", "brew-message", () => ({
      machine_id: Number(document.getElementById("brew-machine").value),
      drink_type: document.getElementById("brew-drink").value,
      timestamp: document.getElementById("brew-timestamp").value,
    }))
  );

  document.getElementById("maintenance-form").addEventListener("submit", (event) =>
    submitForm(event, "/api/maintenance", "maintenance-message", () => ({
      machine_id: Number(document.getElementById("maintenance-machine").value),
      type: document.getElementById("maintenance-type").value,
      timestamp: document.getElementById("maintenance-timestamp").value,
      note: document.getElementById("maintenance-note").value || null,
    }))
  );
}

async function submitForm(event, url, messageId, buildPayload) {
  event.preventDefault();
  const message = document.getElementById(messageId);
  message.textContent = "";
  message.className = "message";
  try {
    await fetchJSON(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    message.textContent = "Logged.";
    message.classList.add("ok");
    await loadDashboard();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

function setDefaultDateRange() {
  const today = new Date();
  const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

  const formatDate = (date) => date.toISOString().split('T')[0];
  document.getElementById("filter-from").value = formatDate(thirtyDaysAgo);
  document.getElementById("filter-to").value = formatDate(today);
}

setDefaultDateRange();
loadDashboard().catch((error) => {
  document.getElementById("total-brews").textContent = "!";
  console.error("Dashboard failed to load:", error);
});
if (!LOBBY_MODE) {
  setupForms().catch((error) => console.error("Form setup failed:", error));
  loadAlerts().catch((error) => console.error("Alerts failed to load:", error));

  setInterval(() => {
    loadAlerts().catch((error) => console.error("Alerts refresh failed:", error));
  }, 60000); // 60s poll
}

// Date filter event listeners
document.getElementById("filter-from").addEventListener("change", loadDashboard);
document.getElementById("filter-to").addEventListener("change", loadDashboard);
document.getElementById("filter-clear").addEventListener("click", () => {
  document.getElementById("filter-from").value = "";
  document.getElementById("filter-to").value = "";
  loadDashboard();
});
