const form = document.querySelector("#simulate-form");
const promptInput = document.querySelector("#prompt");
const statusEl = document.querySelector("#status");
const headlineEl = document.querySelector("#headline");
const summaryEl = document.querySelector("#summary");
const alertsEl = document.querySelector("#alerts");
const recommendationsEl = document.querySelector("#recommendations");
const chartTitleEl = document.querySelector("#chart-title");
const canvas = document.querySelector("#forecast-chart");
const ctx = canvas.getContext("2d");

const metricEls = {
  congestion: document.querySelector("#metric-congestion"),
  footfall: document.querySelector("#metric-footfall"),
  air: document.querySelector("#metric-air"),
  cycle: document.querySelector("#metric-cycle"),
};

function pct(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function setStatus(text) {
  statusEl.textContent = text;
}

function drawChart(chart) {
  const width = canvas.width;
  const height = canvas.height;
  const pad = { top: 24, right: 20, bottom: 42, left: 44 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const series = [
    ["congestion", chart.congestion, "#b9473a"],
    ["footfall", chart.footfall, "#315f96"],
    ["air_quality", chart.air_quality, "#b77a14"],
    ["cycleDemand", chart.cycleDemand, "#166a5b"],
  ];

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d8ded8";
  ctx.lineWidth = 1;
  ctx.font = "13px system-ui, sans-serif";
  ctx.fillStyle = "#6d7670";

  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillText(`${100 - i * 25}%`, 8, y + 4);
  }

  const labels = chart.labels || [];
  labels.forEach((label, index) => {
    const x = pad.left + (plotW / Math.max(labels.length - 1, 1)) * index;
    ctx.fillText(label, x - 14, height - 14);
  });

  series.forEach(([, values, color]) => {
    if (!values || values.length === 0) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = pad.left + (plotW / Math.max(values.length - 1, 1)) * index;
      const y = pad.top + plotH - Number(value) * plotH;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
}

function renderList(target, rows, renderer, emptyText) {
  if (!rows || rows.length === 0) {
    target.className = "list muted";
    target.textContent = emptyText;
    return;
  }
  target.className = "list";
  target.innerHTML = rows.map(renderer).join("");
}

function render(data) {
  headlineEl.textContent = data.headline.title;
  summaryEl.textContent = data.headline.summary;
  chartTitleEl.textContent = data.scenario.label;

  metricEls.congestion.textContent = pct(data.averages.congestion);
  metricEls.footfall.textContent = pct(data.averages.footfall);
  metricEls.air.textContent = pct(data.averages.air_quality);
  metricEls.cycle.textContent = pct(data.averages.cycle_demand);

  renderList(
    alertsEl,
    data.alerts,
    (alert) => `
      <div class="item">
        <strong>${alert.risk_level} ${alert.outcome.replaceAll("_", " ")}</strong>
        <span>${alert.location_id.replaceAll("_", " ")} at ${alert.time.slice(11, 16)} · ${pct(alert.risk_score)}</span>
      </div>
    `,
    "No high-risk alerts for this run."
  );

  renderList(
    recommendationsEl,
    data.recommendations,
    (rec) => `
      <div class="item">
        <strong>${rec.title}</strong>
        <p>${rec.action}</p>
      </div>
    `,
    "No recommendations available."
  );

  drawChart(data.chart);
}

async function simulate(event) {
  event.preventDefault();
  setStatus("Running");
  form.querySelector("button").disabled = true;

  try {
    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptInput.value, horizon_hours: 12 }),
    });

    if (!response.ok) {
      throw new Error(`Simulation failed: ${response.status}`);
    }

    render(await response.json());
    setStatus("Complete");
  } catch (error) {
    headlineEl.textContent = "Simulation failed";
    summaryEl.textContent = error.message;
    setStatus("Error");
  } finally {
    form.querySelector("button").disabled = false;
  }
}

form.addEventListener("submit", simulate);
drawChart({ labels: [], congestion: [], footfall: [], air_quality: [], cycleDemand: [] });
