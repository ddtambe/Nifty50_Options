"use strict";

const DATA_ROOTS = ["../data", "./sample"];
const ATM_RANGE = 500; // Show strikes within +/- 500 of spot
let globalIndex = null;
let currentFeed = null;
let allExpiryFeeds = {};

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

function formatNumber(num) {
  if (num >= 100000) return (num / 100000).toFixed(1) + "L";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K";
  return num.toString();
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

  // Set up view toggle
  document.querySelectorAll('input[name="viewMode"]').forEach(radio => {
    radio.onchange = () => renderWalls(currentFeed);
  });
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

  // Load current expiry
  currentFeed = await fetchJson(`${day}/${expiry}.json`);
  document.getElementById("updated").textContent = "Updated: " + (currentFeed.meta.updated_ist || "");

  // Load all expiries for key levels cards
  const dayEntry = globalIndex.days.find(d => d.trade_date === day);
  allExpiryFeeds = {};
  if (dayEntry) {
    for (const exp of dayEntry.expiries.slice(0, 2)) { // Current + next expiry
      try {
        allExpiryFeeds[exp] = await fetchJson(`${day}/${exp}.json`);
      } catch (e) { /* skip if not available */ }
    }
  }

  renderKeyLevels();
  renderWalls(currentFeed);
  renderOiTimeline(currentFeed);
  renderOiHeatmaps(currentFeed);
  renderBuildup(currentFeed);

  const compareDays = getSelectedCompareDays();
  await renderTimelineWithCompare(currentFeed, day, expiry, compareDays);
}

function findKeyLevels(feed) {
  if (!feed || !feed.strikes || feed.strikes.length === 0) return null;

  const timeline = feed.timeline || [];
  const latest = timeline[timeline.length - 1] || {};

  // Find max CE OI (resistance) and max PE OI (support)
  let maxCeOi = 0, maxPeOi = 0, resistance = 0, support = 0;
  feed.strikes.forEach(s => {
    if (s.ce_oi > maxCeOi) { maxCeOi = s.ce_oi; resistance = s.strike; }
    if (s.pe_oi > maxPeOi) { maxPeOi = s.pe_oi; support = s.strike; }
  });

  return {
    spot: latest.spot || 0,
    pcr: latest.pcr || 0,
    maxPain: latest.max_pain || 0,
    resistance,
    resistanceOi: maxCeOi,
    support,
    supportOi: maxPeOi,
    verdict: determineVerdict(latest.spot, latest.max_pain, latest.pcr)
  };
}

function determineVerdict(spot, maxPain, pcr) {
  if (!spot || !maxPain) return "N/A";
  if (spot > maxPain && pcr > 1.0) return "Bullish";
  if (spot < maxPain && pcr < 0.8) return "Bearish";
  return "Rangebound";
}

function createKeyLevelCard(expiry, levels, isNext) {
  const card = document.createElement("div");
  card.className = "key-level-card" + (isNext ? " next-expiry" : "");

  const header = document.createElement("div");
  header.className = "card-header";

  const title = document.createElement("span");
  title.className = "card-title";
  title.textContent = isNext ? "NEXT EXPIRY" : "CURRENT EXPIRY";

  const expiryBadge = document.createElement("span");
  expiryBadge.className = "card-expiry";
  expiryBadge.textContent = expiry;

  header.appendChild(title);
  header.appendChild(expiryBadge);
  card.appendChild(header);

  const metrics = document.createElement("div");
  metrics.className = "card-metrics";

  // Spot
  const spotMetric = createMetric("Spot", levels.spot.toFixed(2), "");
  metrics.appendChild(spotMetric);

  // Max Pain
  const mpMetric = createMetric("Max Pain", levels.maxPain.toString(), "");
  metrics.appendChild(mpMetric);

  // Resistance
  const resMetric = createMetric("Resistance", levels.resistance.toString(), "CE OI: " + formatNumber(levels.resistanceOi), "resistance");
  metrics.appendChild(resMetric);

  // Support
  const supMetric = createMetric("Support", levels.support.toString(), "PE OI: " + formatNumber(levels.supportOi), "support");
  metrics.appendChild(supMetric);

  // PCR
  const pcrMetric = createMetric("PCR", levels.pcr.toFixed(2), levels.pcr > 1 ? "Bullish bias" : levels.pcr < 0.8 ? "Bearish bias" : "Neutral");
  metrics.appendChild(pcrMetric);

  card.appendChild(metrics);

  // Verdict
  const verdictDiv = document.createElement("div");
  verdictDiv.className = "card-verdict";

  const verdictLabel = document.createElement("div");
  verdictLabel.className = "verdict-label";
  verdictLabel.textContent = "VERDICT";

  const verdictValue = document.createElement("div");
  verdictValue.className = "verdict-value verdict-" + levels.verdict.toLowerCase();
  verdictValue.textContent = levels.verdict;

  verdictDiv.appendChild(verdictLabel);
  verdictDiv.appendChild(verdictValue);
  card.appendChild(verdictDiv);

  return card;
}

function createMetric(label, value, sub, extraClass) {
  const div = document.createElement("div");
  div.className = "metric" + (extraClass ? " " + extraClass : "");

  const labelEl = document.createElement("div");
  labelEl.className = "metric-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("div");
  valueEl.className = "metric-value";
  valueEl.textContent = value;

  div.appendChild(labelEl);
  div.appendChild(valueEl);

  if (sub) {
    const subEl = document.createElement("div");
    subEl.className = "metric-sub";
    subEl.textContent = sub;
    div.appendChild(subEl);
  }

  return div;
}

function renderKeyLevels() {
  const container = document.getElementById("keyLevelsGrid");
  clearNode(container);

  const expiries = Object.keys(allExpiryFeeds).sort();

  expiries.forEach((expiry, idx) => {
    const feed = allExpiryFeeds[expiry];
    const levels = findKeyLevels(feed);
    if (levels) {
      const card = createKeyLevelCard(expiry, levels, idx > 0);
      container.appendChild(card);
    }
  });
}

function renderWalls(feed) {
  if (!feed) return;

  const viewMode = document.querySelector('input[name="viewMode"]:checked').value;
  let strikesToShow = feed.strikes;

  if (viewMode === "atm") {
    // Get spot from timeline
    const timeline = feed.timeline || [];
    const latest = timeline[timeline.length - 1] || {};
    const spot = latest.spot || 24500; // fallback

    // Filter to ATM range
    strikesToShow = feed.strikes.filter(s =>
      s.strike >= (spot - ATM_RANGE) && s.strike <= (spot + ATM_RANGE)
    );
  }

  const strikes = strikesToShow.map((r) => r.strike);
  Plotly.newPlot("wallsChart", [
    { x: strikes, y: strikesToShow.map((r) => r.ce_oi), name: "CE OI (resistance)", type: "bar", marker: { color: "#ef4444" } },
    { x: strikes, y: strikesToShow.map((r) => r.pe_oi), name: "PE OI (support)", type: "bar", marker: { color: "#22c55e" } },
  ], {
    barmode: "group",
    paper_bgcolor: "#1e293b",
    plot_bgcolor: "#1e293b",
    font: { color: "#e2e8f0" },
    margin: { t: 10 },
    xaxis: { title: viewMode === "atm" ? "Strikes (ATM ± 500)" : "Strikes (Full Range)" }
  }, { responsive: true });
}

function renderOiTimeline(feed) {
  if (!feed || !feed.timeline) return;

  const t = feed.timeline.map((p) => p.t);
  const ceOi = feed.timeline.map((p) => p.ce_oi_total || 0);
  const peOi = feed.timeline.map((p) => p.pe_oi_total || 0);

  Plotly.newPlot("oiTimelineChart", [
    { x: t, y: ceOi, name: "Total CE OI", type: "scatter", mode: "lines+markers", line: { color: "#ef4444", width: 2 } },
    { x: t, y: peOi, name: "Total PE OI", type: "scatter", mode: "lines+markers", line: { color: "#22c55e", width: 2 } },
  ], {
    paper_bgcolor: "#1e293b",
    plot_bgcolor: "#1e293b",
    font: { color: "#e2e8f0" },
    margin: { t: 10 },
    yaxis: { title: "Open Interest" },
    xaxis: { title: "Time (15-min intervals)" },
    legend: { orientation: "h", y: -0.2 }
  }, { responsive: true });
}

function renderOiHeatmaps(feed) {
  const st = feed && feed.strikes_timeline;
  if (!st || st.length === 0) {
    Plotly.purge("ceHeatmap");
    Plotly.purge("peHeatmap");
    return;
  }

  // X-axis: timestamps in order
  const times = st.map((snap) => snap.t);

  // Y-axis: union of all strikes across snapshots, sorted ascending
  const strikeSet = new Set();
  st.forEach((snap) => snap.rows.forEach((r) => strikeSet.add(r.strike)));
  const strikes = Array.from(strikeSet).sort((a, b) => a - b);

  // Per-snapshot lookup: strike -> {ce_oi, pe_oi}
  const snapMaps = st.map((snap) => {
    const m = {};
    snap.rows.forEach((r) => { m[r.strike] = r; });
    return m;
  });

  // Build z (ΔOI) and customdata (absolute OI) matrices, rows=strikes, cols=times
  const buildMatrices = (leg) => {
    const z = [];
    const abs = [];
    for (const strike of strikes) {
      const zRow = [];
      const absRow = [];
      let prev = null;
      for (let ti = 0; ti < snapMaps.length; ti++) {
        const cur = snapMaps[ti][strike] ? snapMaps[ti][strike][leg] : 0;
        absRow.push(cur);
        zRow.push(prev === null ? 0 : cur - prev); // first column = 0 (no prior)
        prev = cur;
      }
      z.push(zRow);
      abs.push(absRow);
    }
    return { z, abs };
  };

  const diverging = [
    [0, "#ef4444"],   // strong negative -> red
    [0.5, "#1e293b"], // zero -> neutral (theme bg)
    [1, "#22c55e"],   // strong positive -> green
  ];

  const plotLeg = (divId, leg, title) => {
    const { z, abs } = buildMatrices(leg);
    Plotly.newPlot(divId, [{
      type: "heatmap",
      x: times,
      y: strikes,
      z: z,
      customdata: abs,
      colorscale: diverging,
      zmid: 0,
      hovertemplate:
        "Strike: %{y}<br>Time: %{x}<br>ΔOI: %{z:,}<br>Total OI: %{customdata:,}<extra></extra>",
      colorbar: { title: "ΔOI" },
    }], {
      paper_bgcolor: "#1e293b",
      plot_bgcolor: "#1e293b",
      font: { color: "#e2e8f0" },
      margin: { t: 10, l: 60 },
      xaxis: { title: "Time (15-min intervals)" },
      yaxis: { title: "Strike", type: "category" },
    }, { responsive: true });
  };

  plotLeg("ceHeatmap", "ce_oi", "CE");
  plotLeg("peHeatmap", "pe_oi", "PE");
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
    tr.appendChild(cell(formatNumber(r.ce_oi)));
    tr.appendChild(cell(formatNumber(r.ce_chg_oi)));
    tr.appendChild(cell(r.ce_buildup, buildupClass(r.ce_buildup)));
    tr.appendChild(cell(r.pe_buildup, buildupClass(r.pe_buildup)));
    tr.appendChild(cell(formatNumber(r.pe_chg_oi)));
    tr.appendChild(cell(formatNumber(r.pe_oi)));
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
