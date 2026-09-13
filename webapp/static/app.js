"use strict";
// Branchseed web console frontend. Vanilla JS, no build step, no CDN --
// everything here is served from disk by webapp/server.py so the app works
// fully offline. Talks to the 8+ REST endpoints in webapp/server.py; no
// detection logic lives client-side.

// Mirrors webapp/stage_labels.py -- display labels only, not pipeline logic.
const STAGES = [
  ["load", "Load"], ["profile", "Profile"], ["candidates", "Candidates"],
  ["frame", "Frame"], ["instances", "Instances"], ["geometry", "Geometry"], ["export", "Export"],
];
const RUNTIME_BUDGET_S = 60;
const MEMORY_BUDGET_MB = 8192;

const state = {
  caseId: null,
  runId: null,
  imageFile: null,
  maskFile: null,
  overrides: {},
  prediction: null,
  review: {},
  selectedInstanceId: null,
  showRejected: false,
  eventSource: null,
  runStartedAt: null,
  runTimer: null,
  volumeShape: null,
};

const $ = (id) => document.getElementById(id);

function fmt(n, digits = 1) {
  return typeof n === "number" ? n.toFixed(digits) : "—";
}

// ---------- routing ----------

function showView(name) {
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".topnav a").forEach((el) => el.classList.remove("active"));
  const view = $(`view-${name}`);
  if (view) view.classList.add("active");
  const link = document.querySelector(`.topnav a[data-view="${name}"]`);
  if (link) link.classList.add("active");
  if (name === "cases") loadCases();
}

window.addEventListener("hashchange", () => {
  const name = (location.hash || "#upload").slice(1);
  showView(name);
});

// ---------- upload screen ----------

async function loadConfigDefaults() {
  const res = await fetch("/api/config/defaults");
  const cfg = await res.json();
  $("slider-min-extent").value = cfg.min_extent_mm;
  $("slider-trace-cap").value = cfg.trace_max_mm;
  $("slider-min-radius").value = cfg.min_radius_mm;
  $("chk-log-rejections").checked = !!cfg.log_rejections;
  $("val-min-extent").textContent = cfg.min_extent_mm;
  $("val-trace-cap").textContent = cfg.trace_max_mm;
  $("val-min-radius").textContent = cfg.min_radius_mm;
}

function wireSlider(sliderId, labelId, key) {
  const slider = $(sliderId);
  slider.addEventListener("input", () => {
    $(labelId).textContent = slider.value;
    state.overrides[key] = parseFloat(slider.value);
  });
}

function updateRunButton() {
  const ready = state.imageFile && state.maskFile;
  $("btn-run").disabled = !ready;
  $("run-hint").textContent = ready
    ? "Ready to upload and run."
    : "Choose a CT volume and a mask to continue.";
}

function wireUploadScreen() {
  $("file-image").addEventListener("change", (e) => {
    state.imageFile = e.target.files[0] || null;
    $("image-state").textContent = state.imageFile ? "selected" : "not selected";
    $("image-name").textContent = state.imageFile ? state.imageFile.name : "drop or click to choose";
    updateRunButton();
  });
  $("file-mask").addEventListener("change", (e) => {
    state.maskFile = e.target.files[0] || null;
    $("mask-state").textContent = state.maskFile ? "selected" : "not selected";
    $("mask-name").textContent = state.maskFile ? state.maskFile.name : "binary · 1 = aorta";
    updateRunButton();
  });
  wireSlider("slider-min-extent", "val-min-extent", "min_extent_mm");
  wireSlider("slider-trace-cap", "val-trace-cap", "trace_max_mm");
  wireSlider("slider-min-radius", "val-min-radius", "min_radius_mm");
  $("chk-log-rejections").addEventListener("change", (e) => {
    state.overrides.log_rejections = e.target.checked;
  });
  $("btn-run").addEventListener("click", submitCase);
}

async function submitCase() {
  $("btn-run").disabled = true;
  $("run-hint").textContent = "Uploading…";
  const form = new FormData();
  form.append("image", state.imageFile);
  form.append("mask", state.maskFile);
  let res = await fetch("/api/cases", { method: "POST", body: form });
  if (!res.ok) {
    $("run-hint").textContent = "Upload failed.";
    $("btn-run").disabled = false;
    return;
  }
  const { case_id } = await res.json();
  state.caseId = case_id;

  res = await fetch(`/api/cases/${case_id}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.overrides),
  });
  if (!res.ok) {
    $("run-hint").textContent = "Failed to start run.";
    $("btn-run").disabled = false;
    return;
  }
  const { run_id } = await res.json();
  state.runId = run_id;
  updateRunButton();
  location.hash = "#run";
  startRunMonitor(case_id, run_id, state.imageFile.name);
}

// ---------- run monitor screen ----------

function renderStageRow(activeStage, doneStages) {
  const row = $("stage-row");
  row.innerHTML = "";
  STAGES.forEach(([key, label]) => {
    const div = document.createElement("div");
    div.className = "stage";
    if (doneStages.has(key)) div.classList.add("done");
    if (key === activeStage) div.classList.add("active");
    div.textContent = label;
    row.appendChild(div);
  });
}

function appendLogLine(text) {
  const panel = $("log-panel");
  const line = document.createElement("div");
  line.textContent = text;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}

function startRunMonitor(caseId, runId, displayName) {
  $("run-case-id").textContent = displayName || caseId;
  $("run-id-label").textContent = `case ${caseId} · run ${runId.slice(0, 8)}`;
  $("log-panel").innerHTML = "";
  $("btn-view-results").disabled = true;
  $("budget-runtime").textContent = `0.0 s / ${RUNTIME_BUDGET_S} s target`;
  $("budget-runtime-fill").style.width = "0%";
  $("budget-memory").textContent = "measuring…";
  $("budget-memory-fill").style.width = "0%";

  const doneStages = new Set();
  renderStageRow(null, doneStages);

  state.runStartedAt = Date.now();
  if (state.runTimer) clearInterval(state.runTimer);
  state.runTimer = setInterval(() => {
    const elapsed = (Date.now() - state.runStartedAt) / 1000;
    $("budget-runtime").textContent = `${elapsed.toFixed(1)} s / ${RUNTIME_BUDGET_S} s target`;
    $("budget-runtime-fill").style.width = `${Math.min(100, (elapsed / RUNTIME_BUDGET_S) * 100)}%`;
  }, 250);

  if (state.eventSource) state.eventSource.close();
  const es = new EventSource(`/api/runs/${runId}/events`);
  state.eventSource = es;
  es.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    if (event.type === "stage") {
      if (state.currentStage) doneStages.add(state.currentStage);
      state.currentStage = event.stage;
      renderStageRow(event.stage, doneStages);
      appendLogLine(`[${new Date(event.t * 1000).toLocaleTimeString()}] ${event.label}`);
    } else if (event.type === "status" && event.message) {
      appendLogLine(event.message);
    } else if (event.type === "error") {
      appendLogLine(`ERROR: ${event.message}`);
      clearInterval(state.runTimer);
      es.close();
    } else if (event.type === "done") {
      if (state.currentStage) doneStages.add(state.currentStage);
      renderStageRow(null, doneStages);
      appendLogLine(
        `done: ${event.n_daughters} daughter(s), ${event.n_excluded_candidates} excluded, ` +
        `${event.runtime_s.toFixed(1)}s, ${event.peak_memory_mb.toFixed(0)} MB peak`,
      );
      $("budget-memory").textContent = `${event.peak_memory_mb.toFixed(0)} MB / ${MEMORY_BUDGET_MB} MB`;
      $("budget-memory-fill").style.width = `${Math.min(100, (event.peak_memory_mb / MEMORY_BUDGET_MB) * 100)}%`;
      clearInterval(state.runTimer);
      $("btn-view-results").disabled = false;
      es.close();
    } else if (event.type === "status" && event.state) {
      // terminal replay marker, nothing to render beyond what done/error already did
    }
  };
}

$("btn-view-results")?.addEventListener("click", () => {
  location.hash = "#review";
  loadReview(state.caseId, state.runId);
});

// ---------- review screen ----------

function branchLabel(d) {
  return `${d.instance_id}`;
}

function renderBranchList() {
  const rowsEl = $("branch-rows");
  rowsEl.innerHTML = "";
  const daughters = state.prediction.daughters || [];
  $("empty-state").style.display = daughters.length === 0 ? "block" : "none";
  daughters.forEach((d) => {
    const row = document.createElement("div");
    row.className = "branch-row" + (d.instance_id === state.selectedInstanceId ? " selected" : "");
    row.innerHTML = `
      <div class="branch-row-head"><span>${branchLabel(d)}</span><span>r ${fmt(d.radius_mm)} mm</span></div>
      <div class="branch-row-meta">clock ${fmt(d.clock_position)}h · conf ${fmt(d.confidence, 2)}</div>
    `;
    row.addEventListener("click", () => selectBranch(d.instance_id));
    rowsEl.appendChild(row);
  });
}

function renderRejectedDrawer() {
  const drawer = $("rejected-drawer");
  const excluded = state.prediction.excluded_candidates || [];
  drawer.innerHTML = "";
  excluded.forEach((e) => {
    const row = document.createElement("div");
    row.className = "rejected-row";
    row.textContent = `${e.reason || "excluded"} · ostium ${JSON.stringify(e.ostium_xyz_mm)}`;
    drawer.appendChild(row);
  });
  $("btn-toggle-rejected").textContent = `${state.showRejected ? "Hide" : "Show"} rejected (${excluded.length}) ${state.showRejected ? "" : "→"}`;
  drawer.style.display = state.showRejected ? "flex" : "none";
}

function decisionKey(instanceId) {
  return `${state.runId}:${instanceId}`;
}

function renderInspector() {
  const el = $("inspector");
  const d = (state.prediction.daughters || []).find((x) => x.instance_id === state.selectedInstanceId);
  if (!d) {
    el.innerHTML = '<div class="inspector-empty muted small">Select a branch to inspect it.</div>';
    return;
  }
  const decision = (state.review[decisionKey(d.instance_id)] || {}).decision;
  el.innerHTML = `
    <div class="inspector-row" style="justify-content:space-between"><strong>${d.instance_id}</strong></div>
    <div class="inspector-grid">
      <div class="inspector-tile"><div class="tl">RADIUS</div><div class="tv">${fmt(d.radius_mm)} mm</div></div>
      <div class="inspector-tile"><div class="tl">TAKEOFF ANGLE</div><div class="tv">${fmt(d.takeoff_angle_deg, 0)}&deg;</div></div>
    </div>
    <div class="params-label">PHYSICAL COORDINATES (mm)</div>
    <div class="inspector-row"><span class="k">ostium_xyz_mm</span><span>${JSON.stringify(d.ostium_xyz_mm.map((v) => +v.toFixed(1)))}</span></div>
    <div class="inspector-row"><span class="k">seed_xyz_mm</span><span>${JSON.stringify(d.seed_xyz_mm.map((v) => +v.toFixed(1)))}</span></div>
    <div class="inspector-row"><span class="k">direction_xyz</span><span>${JSON.stringify(d.direction_xyz.map((v) => +v.toFixed(2)))}</span></div>
    <div class="inspector-row"><span class="k">clock_position</span><span>${fmt(d.clock_position)} h</span></div>
    <div class="inspector-row"><span class="k">arclen_from_top_mm</span><span>${fmt(d.arclen_from_top_mm)} mm</span></div>
    <div class="decision-row">
      <div class="btn-decision confirm ${decision === "confirmed" ? "active" : ""}" data-decision="confirmed">Confirm</div>
      <div class="btn-decision reject ${decision === "rejected" ? "active" : ""}" data-decision="rejected">Reject</div>
    </div>
  `;
  el.querySelectorAll(".btn-decision").forEach((btn) => {
    btn.addEventListener("click", () => submitReview(d.instance_id, btn.dataset.decision));
  });
}

async function submitReview(instanceId, decision) {
  await fetch(`/api/cases/${state.caseId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: state.runId, instance_id: instanceId, decision }),
  });
  state.review = await (await fetch(`/api/cases/${state.caseId}/review`)).json();
  renderInspector();
}

function selectBranch(instanceId) {
  state.selectedInstanceId = instanceId;
  renderBranchList();
  renderInspector();
}

async function updateSlice(z) {
  $("slice-img").src = `/api/cases/${state.caseId}/slice?z=${z}`;
  $("slice-label").textContent = `slice ${z}${state.volumeShape ? ` / ${state.volumeShape[0] - 1}` : ""}`;
}

async function loadReview(caseId, runId) {
  state.caseId = caseId;
  state.runId = runId;
  state.selectedInstanceId = null;
  state.showRejected = false;

  const [predRes, reviewRes, volRes] = await Promise.all([
    fetch(`/api/cases/${caseId}/prediction?run_id=${runId}`),
    fetch(`/api/cases/${caseId}/review`),
    fetch(`/api/cases/${caseId}/volume-info`),
  ]);
  state.prediction = await predRes.json();
  state.review = await reviewRes.json();
  const vol = await volRes.json();
  state.volumeShape = vol.shape_zyx;

  $("review-case-id").textContent = state.prediction.case_id || caseId;
  const n = (state.prediction.daughters || []).length;
  const runtime = state.prediction.meta ? fmt(state.prediction.meta.runtime_s) : "—";
  $("review-summary").textContent = `${n} daughter${n === 1 ? "" : "s"} · ${runtime} s`;
  $("btn-export").href = `/api/cases/${caseId}/export?run_id=${runId}`;

  $("overlay-img").src = `/api/cases/${caseId}/overlay?run_id=${runId}`;
  $("origin-map-img").src = `/api/cases/${caseId}/origin-map?run_id=${runId}`;
  $("json-block").textContent = JSON.stringify(state.prediction, null, 2);

  const slider = $("slice-slider");
  slider.max = String(Math.max(0, state.volumeShape[0] - 1));
  slider.value = String(Math.floor(state.volumeShape[0] / 2));
  updateSlice(slider.value);

  renderBranchList();
  renderRejectedDrawer();
  renderInspector();
}

function wireReviewScreen() {
  $("slice-slider").addEventListener("input", (e) => updateSlice(e.target.value));
  $("btn-toggle-rejected").addEventListener("click", () => {
    state.showRejected = !state.showRejected;
    renderRejectedDrawer();
  });
  $("btn-copy-json").addEventListener("click", () => {
    navigator.clipboard.writeText($("json-block").textContent);
  });
}

// ---------- case library screen ----------

function statusLabel(status) {
  const labels = { done: "complete", running: "running", queued: "queued", error: "error", no_runs: "no runs yet" };
  return labels[status] || status;
}

async function loadCases() {
  const res = await fetch("/api/cases");
  const { cases } = await res.json();
  const rowsEl = $("cases-rows");
  rowsEl.innerHTML = "";
  cases.forEach((c) => {
    const row = document.createElement("div");
    row.className = "case-row";
    row.innerHTML = `
      <span style="font-family:ui-monospace,monospace">${c.case_id}</span>
      <span class="status-${c.status}">${statusLabel(c.status)}</span>
      <span>${c.n_daughters === null ? "—" : c.n_daughters}</span>
      <span>${c.runtime_s === null ? "—" : fmt(c.runtime_s) + " s"}</span>
      <span>${c.peak_memory_mb === null ? "—" : Math.round(c.peak_memory_mb) + " MB"}</span>
      <span style="text-align:right;color:var(--accent)">${c.latest_run_id ? "Review →" : ""}</span>
    `;
    if (c.latest_run_id && (c.status === "done" || c.status === "error")) {
      row.addEventListener("click", () => {
        location.hash = "#review";
        loadReview(c.case_id, c.latest_run_id);
      });
    } else if (c.latest_run_id) {
      row.addEventListener("click", () => {
        location.hash = "#run";
        startRunMonitor(c.case_id, c.latest_run_id, c.original_image_name);
      });
    }
    rowsEl.appendChild(row);
  });
}

// ---------- init ----------

wireUploadScreen();
wireReviewScreen();
loadConfigDefaults();
showView((location.hash || "#upload").slice(1));
