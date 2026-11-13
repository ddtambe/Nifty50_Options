"use strict";

// --- Strike History: TradingView-style continuous chart across ALL days ---
// Stitches every saved day's `strikes_timeline` for the selected expiry into one
// time series per strike, so past + present LTP / OI read as a single chart.
// Overnight hours and every no-data day (weekends, holidays, missed fetches)
// are collapsed via Plotly rangebreaks so sessions sit edge to edge.
//
// Depends on globals from app.js: fetchJson, globalIndex, clearNode, formatNumber,
// CHART_CONFIG, CHART_INTERACTION_LAYOUT, CHART_THEME.

const HISTORY_MARKET_OPEN_HR = 9.25;        // 09:15 IST
const HISTORY_MARKET_CLOSE_HR = 15.5;       // 15:30 IST
const HISTORY_SESSION_OPEN = "09:15";
const HISTORY_SESSION_MS = (HISTORY_MARKET_CLOSE_HR - HISTORY_MARKET_OPEN_HR) * 3600 * 1000;

const historyState = {
  expiry: null,
  feeds: [],                 // [{day, feed}] sorted by day
  strikes: [],               // union of strikes across feeds, ascending
  selected: null,            // the ONE strike on the chart (TradingView-style)
  leg: "both",               // "ce" | "pe" | "both" | "straddle"
};
const historyFeedCache = new Map(); // `${day}/${expiry}` -> feed

async function loadHistoryFeeds(expiry) {
  const days = ((globalIndex && globalIndex.days) || [])
    .filter((d) => d.expiries.includes(expiry))
    .map((d) => d.trade_date)
    .sort();
  const results = await Promise.all(days.map(async (day) => {
    const key = `${day}/${expiry}`;
    // The latest day is still updating, so never trust its cached copy.
    const isLatest = day === days[days.length - 1];
    if (!isLatest && historyFeedCache.has(key)) return { day, feed: historyFeedCache.get(key) };
    try {
      const feed = await fetchJson(`${key}.json`);
      historyFeedCache.set(key, feed);
      return { day, feed };
    } catch (e) {
      console.warn(`Strike history: could not load ${key}`, e);
      return null;
    }
  }));
  return results.filter(Boolean);
}

function historyStrikeUnion(feeds) {
  const set = new Set();
  feeds.forEach(({ feed }) => (feed.strikes_timeline || [])
    .forEach((snap) => snap.rows.forEach((r) => set.add(r.strike))));
  return Array.from(set).sort((a, b) => a - b);
}

function historyLatestSpot(feeds) {
  for (let i = feeds.length - 1; i >= 0; i--) {
    const tl = feeds[i].feed.timeline || [];
    if (tl.length) return tl[tl.length - 1].spot;
  }
  return null;
}

function historyAtmStrike(strikes, spot) {
  if (!strikes.length) return null;
  if (spot == null) return strikes[Math.floor(strikes.length / 2)];
  return strikes.reduce((best, s) => (Math.abs(s - spot) < Math.abs(best - spot) ? s : best), strikes[0]);
}

function historySelectStrike(strike) {
  historyState.selected = strike;
  renderHistoryControls();
  drawHistoryChart();
}

// One continuous series per strike: {t[], ce_ltp[], pe_ltp[], ce_oi[], pe_oi[]}.
// Missing values stay null so Plotly breaks the line instead of drawing a fake 0.
function historySeries(feeds, strike) {
  const out = { t: [], ce_ltp: [], pe_ltp: [], ce_oi: [], pe_oi: [], ce_volume: [], pe_volume: [] };
  const num = (v) => (typeof v === "number" ? v : null);
  // LTP 0 = the contract hasn't traded yet, not a real ₹0 price — leave a gap.
  const price = (v) => (typeof v === "number" && v > 0 ? v : null);
  feeds.forEach(({ feed }) => (feed.strikes_timeline || []).forEach((snap) => {
    const row = snap.rows.find((r) => r.strike === strike);
    out.t.push(snap.t);
    ["ce_ltp", "pe_ltp"].forEach((k) => out[k].push(row ? price(row[k]) : null));
    ["ce_oi", "pe_oi", "ce_volume", "pe_volume"].forEach((k) => out[k].push(row ? num(row[k]) : null));
  }));
  return out;
}

function historySpotSeries(feeds) {
  const t = [];
  const spot = [];
  feeds.forEach(({ feed }) => (feed.timeline || []).forEach((p) => {
    t.push(p.t);
    spot.push(p.spot);
  }));
  return { t, spot };
}

// Calendar days between the first and last loaded day with no data (weekends,
// holidays, missed fetches). Returned as each day's session-open timestamp so
// the caller can collapse exactly that session window; the overnight hour break
// already hides the rest. (A whole-day `values` break overlaps the hour break
// and crashes Plotly, so never use dvalue = 24h here.)
function historyMissingSessions(days) {
  if (days.length < 2) return [];
  const have = new Set(days);
  const missing = [];
  const [y, m, d] = days[0].split("-").map(Number);
  const cur = new Date(y, m - 1, d);
  const last = days[days.length - 1];
  const fmt = (dt) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
  while (fmt(cur) < last) {
    const s = fmt(cur);
    if (!have.has(s)) missing.push(`${s} ${HISTORY_SESSION_OPEN}`);
    cur.setDate(cur.getDate() + 1);
  }
  return missing;
}

function historyLegTraces(series, strike) {
  const LEG_COLOR = { ce: "#dc2626", pe: "#16a34a", straddle: "#2563eb" };
  const traces = [];
  const ltpHover = (label) => `${strike} ${label}<br>%{x}<br>LTP ₹%{y:,.2f}<extra></extra>`;
  const oiHover = (label) => `${strike} ${label}<br>%{x}<br>OI %{y:,}<extra></extra>`;
  const legs = historyState.leg === "both" ? ["ce", "pe"] : [historyState.leg];

  if (historyState.leg === "straddle") {
    const prem = series.ce_ltp.map((c, i) => (c != null && series.pe_ltp[i] != null ? c + series.pe_ltp[i] : null));
    const oi = series.ce_oi.map((c, i) => (c != null && series.pe_oi[i] != null ? c + series.pe_oi[i] : null));
    traces.push({ x: series.t, y: prem, name: `${strike} CE+PE`, legendgroup: String(strike),
      type: "scatter", mode: "lines", line: { color: LEG_COLOR.straddle, width: 2 }, yaxis: "y",
      hovertemplate: ltpHover("CE+PE") });
    traces.push({ x: series.t, y: oi, name: `${strike} OI`, legendgroup: String(strike), showlegend: false,
      type: "scatter", mode: "lines", fill: "tozeroy", line: { color: LEG_COLOR.straddle, width: 1.5 }, yaxis: "y3",
      hovertemplate: oiHover("CE+PE") });
    return traces;
  }

  legs.forEach((leg) => {
    const label = leg.toUpperCase();
    const color = LEG_COLOR[leg];
    traces.push({ x: series.t, y: series[`${leg}_ltp`], name: `${strike} ${label}`,
      legendgroup: leg, type: "scatter", mode: "lines",
      line: { color, width: 2 }, yaxis: "y", hovertemplate: ltpHover(label) });
    traces.push({ x: series.t, y: series[`${leg}_oi`], name: `${strike} ${label} OI`,
      legendgroup: leg, showlegend: false, type: "scatter", mode: "lines",
      line: { color, width: 1.5 }, yaxis: "y3", hovertemplate: oiHover(label) });
  });
  return traces;
}

function renderHistoryControls() {
  const container = document.getElementById("historyControls");
  clearNode(container);

  const legGroup = document.createElement("div");
  legGroup.className = "history-legs";
  [["ce", "CE"], ["pe", "PE"], ["both", "CE + PE"], ["straddle", "Straddle (CE+PE sum)"]].forEach(([val, text]) => {
    const lbl = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "historyLeg";
    input.value = val;
    input.checked = historyState.leg === val;
    input.onchange = () => { historyState.leg = val; drawHistoryChart(); };
    lbl.appendChild(input);
    lbl.appendChild(document.createTextNode(" " + text));
    legGroup.appendChild(lbl);
  });
  container.appendChild(legGroup);

  const strikeRow = document.createElement("div");
  strikeRow.className = "history-strikes";
  const label = document.createElement("span");
  label.className = "compare-label";
  label.textContent = "Strikes:";
  strikeRow.appendChild(label);
  const idx = historyState.strikes.indexOf(historyState.selected);
  const step = (text, delta, title) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "strike-chip strike-chip--action";
    btn.textContent = text;
    btn.title = title;
    const target = historyState.strikes[idx + delta];
    btn.disabled = target === undefined;
    btn.onclick = () => historySelectStrike(target);
    return btn;
  };
  strikeRow.appendChild(step("‹", -1, "Previous (lower) strike"));
  historyState.strikes.forEach((strike) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "strike-chip";
    chip.textContent = strike;
    const on = historyState.selected === strike;
    chip.classList.toggle("is-selected", on);
    chip.setAttribute("aria-pressed", on ? "true" : "false");
    chip.onclick = () => historySelectStrike(strike);
    strikeRow.appendChild(chip);
  });
  strikeRow.appendChild(step("›", 1, "Next (higher) strike"));
  container.appendChild(strikeRow);
}

function drawHistoryChart() {
  const div = "historyChart";
  const { feeds } = historyState;
  const strike = historyState.selected;
  if (!feeds.length || strike == null) {
    Plotly.purge(div);
    document.getElementById(div).textContent = "No history for this expiry yet.";
    return;
  }
  document.getElementById(div).textContent = "";

  const traces = historyLegTraces(historySeries(feeds, strike), strike);
  const spot = historySpotSeries(feeds);
  traces.push({ x: spot.t, y: spot.spot, name: "Nifty spot", type: "scatter", mode: "lines",
    line: { color: "#94a3b8", width: 1.5 }, yaxis: "y2",
    hovertemplate: "Spot %{y:,.2f}<extra></extra>" });

  const days = feeds.map((f) => f.day);
  const rangebreaks = [{ bounds: [HISTORY_MARKET_CLOSE_HR, HISTORY_MARKET_OPEN_HR], pattern: "hour" }];
  const missing = historyMissingSessions(days);
  if (missing.length) rangebreaks.push({ values: missing, dvalue: HISTORY_SESSION_MS });

  // Faint vertical separators at each session open so day boundaries are visible.
  const shapes = days.slice(1).map((d) => ({
    type: "line", xref: "x", yref: "paper", x0: `${d} ${HISTORY_SESSION_OPEN}`, x1: `${d} ${HISTORY_SESSION_OPEN}`, y0: 0, y1: 1,
    line: { color: "#cbd5e1", width: 1, dash: "dot" },
  }));

  Plotly.newPlot(div, traces, {
    ...CHART_INTERACTION_LAYOUT,
    ...CHART_THEME,
    height: 620,
    margin: { t: 40, r: 60, l: 70 },
    hovermode: "x unified",
    shapes,
    xaxis: {
      type: "date", rangebreaks, fixedrange: false, anchor: "y3",
      tickformat: "%d %b\n%H:%M", showspikes: true, spikemode: "across", spikethickness: 1,
      rangeselector: { x: 0, y: 1.06, buttons: [
        { count: 1, label: "1D", step: "day", stepmode: "backward" },
        { count: 3, label: "3D", step: "day", stepmode: "backward" },
        { count: 7, label: "1W", step: "day", stepmode: "backward" },
        { step: "all", label: "All" },
      ] },
    },
    title: { text: `Strike ${strike}`, x: 0.5, font: { size: 15 } },
    yaxis: { title: historyState.leg === "straddle" ? "Straddle ₹" : "Option LTP ₹", domain: [0.38, 1], fixedrange: false },
    yaxis2: { title: "Spot", overlaying: "y", side: "right", showgrid: false, fixedrange: false },
    yaxis3: { title: "Open Interest", domain: [0, 0.3], fixedrange: false, tickformat: "~s" },
    legend: { orientation: "h", y: -0.12 },
  }, CHART_CONFIG);
}

// Entry point called from app.js whenever the expiry (or day list) changes.
async function renderStrikeHistory(expiry) {
  if (!expiry) return;
  const expiryChanged = historyState.expiry !== expiry;
  historyState.expiry = expiry;
  historyState.feeds = await loadHistoryFeeds(expiry);
  historyState.strikes = historyStrikeUnion(historyState.feeds);

  // Keep the user's strike across refreshes; reset to ATM on a new expiry.
  if (expiryChanged || !historyState.strikes.includes(historyState.selected)) {
    historyState.selected = historyAtmStrike(historyState.strikes, historyLatestSpot(historyState.feeds));
  }

  const days = historyState.feeds.map((f) => f.day);
  document.getElementById("historyRange").textContent = days.length
    ? `${days.length} day(s): ${days[0]} → ${days[days.length - 1]}`
    : "";
  renderHistoryControls();
  drawHistoryChart();
}
