"use strict";

const DATA_ROOTS = ["../data", "./sample"];
let globalIndex = null;

async function fetchJson(path) {
  for (const root of DATA_ROOTS) {
    try {
      const res = await fetch(`${root}/${path}`, { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (_) { /* try next root */ }
  }
  throw new Error(`could not load ${path}`);
}

function buildupClass(label) {
  return "bu-" + label.toLowerCase().replace(/\s+/g, "-").replace(/\//g, "");
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function option(value) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = value;
  return o;
}

async function loadIndex() {
  globalIndex = await fetchJson("index.json");
  const daySel = document.getElementById("daySelect");
  clearNode(daySel);
  globalIndex.days.forEach((d) => daySel.appendChild(option(d.trade_date)));
  daySel.onchange = () => {
    populateExpiries(globalIndex);
    updateCompareCheckboxes();
  };
  if (globalIndex.days.length) daySel.value = globalIndex.days[globalIndex.days.length - 1].trade_date;
  populateExpiries(globalIndex);
  updateCompareCheckboxes();
}

function populateExpiries(idx) {
  const day = document.getElementById("daySelect").value;
  const dayEntry = idx.days.find((d) => d.trade_date === day);
  const expSel = document.getElementById("expirySelect");
  clearNode(expSel);
  (dayEntry ? dayEntry.expiries : []).forEach((e) => expSel.appendChild(option(e)));
  expSel.onchange = () => {
    updateCompareCheckboxes();
    renderSelected();
  };
  renderSelected();
}

function updateCompareCheckboxes() {
  const container = document.getElementById("compareControls");
  clearNode(container);

  if (!globalIndex || globalIndex.days.length < 2) return;

  const currentDay = document.getElementById("daySelect").value;
  const currentExpiry = document.getElementById("expirySelect").value;
  if (!currentExpiry) return;

  const label = document.createElement("span");
  label.textContent = "Compare with: ";
  label.className = "compare-label";
  container.appendChild(label);

  globalIndex.days.forEach((dayEntry) => {
    if (dayEntry.trade_date === currentDay) return;
    if (!dayEntry.expiries.includes(currentExpiry)) return;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = "cmp-" + dayEntry.trade_date;
    checkbox.value = dayEntry.trade_date;
    checkbox.onchange = renderSelected;

    const lbl = document.createElement("label");
    lbl.htmlFor = checkbox.id;
    lbl.textContent = dayEntry.trade_date;

    const wrapper = document.createElement("span");
    wrapper.className = "compare-item";
    wrapper.appendChild(checkbox);
    wrapper.appendChild(lbl);
    container.appendChild(wrapper);
  });
}

function getSelectedCompareDays() {
  const checkboxes = document.querySelectorAll("#compareControls input[type=checkbox]:checked");
  return Array.from(checkboxes).map((cb) => cb.value);
}

async function renderSelected() {
  const day = document.getElementById("daySelect").value;
  const expiry = document.getElementById("expirySelect").value;
  if (!day || !expiry) return;

  const feed = await fetchJson(`${day}/${expiry}.json`);
  document.getElementById("updated").textContent = "Updated: " + (feed.meta.updated_ist || "");
  renderWalls(feed);
  renderBuildup(feed);

  const compareDays = getSelectedCompareDays();
  await renderTimelineWithCompare(feed, day, expiry, compareDays);
}

function renderWalls(feed) {
  const strikes = feed.strikes.map((r) => r.strike);
  Plotly.newPlot("wallsChart", [
    { x: strikes, y: feed.strikes.map((r) => r.ce_oi), name: "CE OI (resistance)", type: "bar", marker: { color: "#ef4444" } },
    { x: strikes, y: feed.strikes.map((r) => r.pe_oi), name: "PE OI (support)", type: "bar", marker: { color: "#22c55e" } },
  ], { barmode: "group", paper_bgcolor: "#1e293b", plot_bgcolor: "#1e293b", font: { color: "#e2e8f0" }, margin: { t: 10 } }, { responsive: true });
}

async function renderTimelineWithCompare(primaryFeed, primaryDay, expiry, compareDays) {
  const traces = [];
  const colors = {
    spot: ["#38bdf8", "#06b6d4", "#0ea5e9", "#22d3ee"],
    maxPain: ["#f59e0b", "#fbbf24", "#f97316", "#eab308"],
    pcr: ["#a78bfa", "#c084fc", "#8b5cf6", "#d946ef"]
  };

  // Primary day traces
  const t = primaryFeed.timeline.map((p) => p.t);
  traces.push({
    x: t,
    y: primaryFeed.timeline.map((p) => p.spot),
    name: `Spot (${primaryDay})`,
    type: "scatter",
    mode: "lines+markers",
    line: { color: colors.spot[0], width: 2 }
  });
  traces.push({
    x: t,
    y: primaryFeed.timeline.map((p) => p.max_pain),
    name: `Max Pain (${primaryDay})`,
    type: "scatter",
    mode: "lines+markers",
    line: { color: colors.maxPain[0], width: 2 }
  });
  traces.push({
    x: t,
    y: primaryFeed.timeline.map((p) => p.pcr),
    name: `PCR (${primaryDay})`,
    type: "scatter",
    mode: "lines+markers",
    yaxis: "y2",
    line: { color: colors.pcr[0], width: 2 }
  });

  // Comparison days
  for (let i = 0; i < compareDays.length; i++) {
    const cmpDay = compareDays[i];
    try {
      const cmpFeed = await fetchJson(`${cmpDay}/${expiry}.json`);
      const cmpT = cmpFeed.timeline.map((p) => p.t);
      const colorIdx = (i + 1) % colors.spot.length;

      traces.push({
        x: cmpT,
        y: cmpFeed.timeline.map((p) => p.spot),
        name: `Spot (${cmpDay})`,
        type: "scatter",
        mode: "lines+markers",
        line: { color: colors.spot[colorIdx], width: 1, dash: "dash" }
      });
      traces.push({
        x: cmpT,
        y: cmpFeed.timeline.map((p) => p.max_pain),
        name: `Max Pain (${cmpDay})`,
        type: "scatter",
        mode: "lines+markers",
        line: { color: colors.maxPain[colorIdx], width: 1, dash: "dash" }
      });
      traces.push({
        x: cmpT,
        y: cmpFeed.timeline.map((p) => p.pcr),
        name: `PCR (${cmpDay})`,
        type: "scatter",
        mode: "lines+markers",
        yaxis: "y2",
        line: { color: colors.pcr[colorIdx], width: 1, dash: "dash" }
      });
    } catch (e) {
      console.warn(`Could not load comparison data for ${cmpDay}/${expiry}:`, e);
    }
  }

  Plotly.newPlot("timelineChart", traces, {
    paper_bgcolor: "#1e293b",
    plot_bgcolor: "#1e293b",
    font: { color: "#e2e8f0" },
    margin: { t: 10 },
    yaxis: { title: "Price" },
    yaxis2: { title: "PCR", overlaying: "y", side: "right" },
    legend: { orientation: "h", y: -0.2 }
  }, { responsive: true });
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function headerRow() {
  const tr = document.createElement("tr");
  ["Strike", "CE OI", "CE ΔOI", "CE Buildup", "PE Buildup", "PE ΔOI", "PE OI", "Zone"]
    .forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      tr.appendChild(th);
    });
  return tr;
}

function renderBuildup(feed) {
  const table = document.createElement("table");
  table.appendChild(headerRow());
  feed.strikes.forEach((r) => {
    const tr = document.createElement("tr");
    tr.appendChild(cell(r.strike));
    tr.appendChild(cell(r.ce_oi));
    tr.appendChild(cell(r.ce_chg_oi));
    tr.appendChild(cell(r.ce_buildup, buildupClass(r.ce_buildup)));
    tr.appendChild(cell(r.pe_buildup, buildupClass(r.pe_buildup)));
    tr.appendChild(cell(r.pe_chg_oi));
    tr.appendChild(cell(r.pe_oi));
    tr.appendChild(cell(r.zone_200pt));
    table.appendChild(tr);
  });
  const container = document.getElementById("buildupTable");
  clearNode(container);
  container.appendChild(table);
}

loadIndex().catch((e) => {
  document.getElementById("updated").textContent = "No data yet: " + e.message;
});
