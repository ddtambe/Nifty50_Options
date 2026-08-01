"use strict";

const DATA_ROOTS = ["../data", "./sample"]; // prod first, local-preview fallback

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
  const idx = await fetchJson("index.json");
  const daySel = document.getElementById("daySelect");
  clearNode(daySel);
  idx.days.forEach((d) => daySel.appendChild(option(d.trade_date)));
  daySel.onchange = () => populateExpiries(idx);
  if (idx.days.length) daySel.value = idx.days[idx.days.length - 1].trade_date;
  populateExpiries(idx);
}

function populateExpiries(idx) {
  const day = document.getElementById("daySelect").value;
  const dayEntry = idx.days.find((d) => d.trade_date === day);
  const expSel = document.getElementById("expirySelect");
  clearNode(expSel);
  (dayEntry ? dayEntry.expiries : []).forEach((e) => expSel.appendChild(option(e)));
  expSel.onchange = renderSelected;
  renderSelected();
}

async function renderSelected() {
  const day = document.getElementById("daySelect").value;
  const expiry = document.getElementById("expirySelect").value;
  if (!day || !expiry) return;
  const feed = await fetchJson(`${day}/${expiry}.json`);
  document.getElementById("updated").textContent = "Updated: " + (feed.meta.updated_ist || "");
  renderWalls(feed);
  renderTimeline(feed);
  renderBuildup(feed);
}

function renderWalls(feed) {
  const strikes = feed.strikes.map((r) => r.strike);
  Plotly.newPlot("wallsChart", [
    { x: strikes, y: feed.strikes.map((r) => r.ce_oi), name: "CE OI (resistance)", type: "bar", marker: { color: "#ef4444" } },
    { x: strikes, y: feed.strikes.map((r) => r.pe_oi), name: "PE OI (support)", type: "bar", marker: { color: "#22c55e" } },
  ], { barmode: "group", paper_bgcolor: "#1e293b", plot_bgcolor: "#1e293b", font: { color: "#e2e8f0" }, margin: { t: 10 } }, { responsive: true });
}

function renderTimeline(feed) {
  const t = feed.timeline.map((p) => p.t);
  Plotly.newPlot("timelineChart", [
    { x: t, y: feed.timeline.map((p) => p.spot), name: "Spot", type: "scatter", mode: "lines+markers", line: { color: "#38bdf8" } },
    { x: t, y: feed.timeline.map((p) => p.max_pain), name: "Max Pain", type: "scatter", mode: "lines+markers", line: { color: "#f59e0b" } },
    { x: t, y: feed.timeline.map((p) => p.pcr), name: "PCR", type: "scatter", mode: "lines+markers", yaxis: "y2", line: { color: "#a78bfa" } },
  ], {
    paper_bgcolor: "#1e293b", plot_bgcolor: "#1e293b", font: { color: "#e2e8f0" }, margin: { t: 10 },
    yaxis: { title: "Price" }, yaxis2: { title: "PCR", overlaying: "y", side: "right" },
  }, { responsive: true });
}

// Build the buildup table with DOM APIs only — NO innerHTML (XSS-safe).
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
