const API_BASE = window.API_BASE || "http://localhost:8000";

const els = {
  bucketName: document.getElementById("bucketName"),
  btnSimulate: document.getElementById("btnSimulate"),
  btnAnalyze: document.getElementById("btnAnalyze"),
  btnPolicy: document.getElementById("btnPolicy"),
  statObjects: document.getElementById("statObjects"),
  statSize: document.getElementById("statSize"),
  statCurrent: document.getElementById("statCurrent"),
  statOptimized: document.getElementById("statOptimized"),
  statSavings: document.getElementById("statSavings"),
  breakdownChart: document.getElementById("breakdownChart"),
  objectsBody: document.getElementById("objectsBody"),
  policyOutput: document.getElementById("policyOutput"),
  healthStatus: document.getElementById("healthStatus"),
};

let lastAnalysis = null;
let currentFilter = "all";

const CLASS_COLORS = {
  STANDARD: "#F2A93C",
  STANDARD_IA: "#E8CB6B",
  ONEZONE_IA: "#D7CE7E",
  GLACIER_IR: "#7EC8E3",
  GLACIER_FR: "#6DDCCF",
  DEEP_ARCHIVE: "#8AA7E8",
};

function money(n) {
  return "$" + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function sizeLabel(kb) {
  if (kb > 1024 * 1024) return (kb / (1024 * 1024)).toFixed(2) + " GB";
  if (kb > 1024) return (kb / 1024).toFixed(1) + " MB";
  return kb.toFixed(0) + " KB";
}

async function checkHealth() {
  try {
    const r = await fetch(`${API_BASE}/api/health`);
    const data = await r.json();
    els.healthStatus.textContent = `backend online · aws credentials ${data.aws_configured ? "detected" : "not configured (demo mode)"}`;
  } catch (e) {
    els.healthStatus.textContent = "backend unreachable — is the API container running?";
  }
}

async function simulate() {
  const bucket = els.bucketName.value.trim() || "demo-analytics-bucket";
  els.btnSimulate.disabled = true;
  els.btnSimulate.textContent = "generating…";
  try {
    await fetch(`${API_BASE}/api/simulate?bucket_name=${encodeURIComponent(bucket)}&num_objects=220`);
    await analyze();
  } finally {
    els.btnSimulate.disabled = false;
    els.btnSimulate.textContent = "New demo data";
  }
}

async function analyze() {
  const bucket = els.bucketName.value.trim() || "demo-analytics-bucket";
  els.btnAnalyze.disabled = true;
  els.btnAnalyze.textContent = "analyzing…";
  try {
    const r = await fetch(`${API_BASE}/api/analyze/${encodeURIComponent(bucket)}`);
    if (!r.ok) throw new Error(await r.text());
    lastAnalysis = await r.json();
    render();
  } catch (e) {
    els.objectsBody.innerHTML = `<tr><td colspan="8">Could not analyze bucket: ${e.message}</td></tr>`;
  } finally {
    els.btnAnalyze.disabled = false;
    els.btnAnalyze.textContent = "Analyze bucket";
  }
}

function render() {
  if (!lastAnalysis) return;
  const a = lastAnalysis;

  els.statObjects.textContent = a.object_count.toLocaleString();
  els.statSize.textContent = a.total_size_gb.toFixed(2) + " GB";
  els.statCurrent.textContent = money(a.total_current_monthly_cost);
  els.statOptimized.textContent = money(a.total_optimized_monthly_cost);
  els.statSavings.textContent = money(a.annual_savings) + ` (${a.savings_pct}%)`;

  renderBreakdown(a.class_breakdown, a.total_optimized_monthly_cost);
  renderTable(a.objects);
}

function renderBreakdown(breakdown, totalCost) {
  const entries = Object.entries(breakdown).sort((x, y) => y[1].monthly_cost - x[1].monthly_cost);
  const maxCost = Math.max(...entries.map(([, v]) => v.monthly_cost), 0.0001);

  els.breakdownChart.innerHTML = entries.map(([cls, v]) => `
    <div class="breakdown-row">
      <span class="breakdown-name">${cls} · ${v.count}</span>
      <div class="breakdown-track">
        <div class="breakdown-fill" style="width:${(v.monthly_cost / maxCost) * 100}%; background:${CLASS_COLORS[cls] || "#888"}"></div>
      </div>
      <span class="breakdown-cost">${money(v.monthly_cost)}</span>
    </div>
  `).join("");
}

function renderTable(objects) {
  let filtered = objects;
  if (currentFilter === "changed") filtered = objects.filter(o => o.changed);
  if (currentFilter === "unchanged") filtered = objects.filter(o => !o.changed);

  filtered = filtered.slice().sort((a, b) => b.monthly_savings - a.monthly_savings).slice(0, 300);

  els.objectsBody.innerHTML = filtered.map(o => `
    <tr>
      <td class="key-cell" title="${o.key}">${o.key}</td>
      <td>${sizeLabel(o.size_kb)}</td>
      <td>${o.age_days}d</td>
      <td>${o.access_count_30d}</td>
      <td><span class="class-pill pill-${o.current_class}">${o.current_class}</span></td>
      <td class="arrow">${o.changed ? "→" : ""}</td>
      <td>${o.changed ? `<span class="class-pill pill-${o.recommended_class}">${o.recommended_class}</span>` : "<span style='color:var(--text-dim)'>—</span>"}</td>
      <td class="${o.monthly_savings > 0 ? "savings-positive" : "savings-zero"}">${o.monthly_savings > 0 ? money(o.monthly_savings) : "—"}</td>
    </tr>
  `).join("") || `<tr><td colspan="8">No objects match this filter.</td></tr>`;
}

async function generatePolicy() {
  if (!lastAnalysis) return;
  els.btnPolicy.disabled = true;
  try {
    const r = await fetch(`${API_BASE}/api/lifecycle-policy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bucket_name: lastAnalysis.bucket }),
    });
    const data = await r.json();
    els.policyOutput.textContent = JSON.stringify(data, null, 2);
  } finally {
    els.btnPolicy.disabled = false;
  }
}

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    currentFilter = chip.dataset.filter;
    if (lastAnalysis) renderTable(lastAnalysis.objects);
  });
});

els.btnSimulate.addEventListener("click", simulate);
els.btnAnalyze.addEventListener("click", analyze);
els.btnPolicy.addEventListener("click", generatePolicy);

checkHealth();
simulate();
