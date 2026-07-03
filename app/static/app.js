const state = {
  currentRunId: null,
  pollHandle: null,
};

function tokenHeaders() {
  const token = document.getElementById("adminToken").value.trim();
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Admin-Token"] = token;
  }
  return headers;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...tokenHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail || "Request failed");
  }
  return response.json();
}

function renderRun(run) {
  state.currentRunId = run.id;
  document.getElementById("runSummary").innerHTML = `
    <p><strong>Area:</strong> ${run.area}</p>
    <p><strong>Status:</strong> ${run.status}</p>
    <p><strong>Created:</strong> ${new Date(run.created_at).toLocaleString()}</p>
  `;

  const statusCounts = {};
  for (const task of run.tasks) {
    statusCounts[task.status] = (statusCounts[task.status] || 0) + 1;
  }

  document.getElementById("agentStatus").innerHTML = Object.entries(statusCounts)
    .map(([status, count]) => `<div class="status-card"><strong>${status}</strong><span>${count} task(s)</span></div>`)
    .join("");

  const queued = run.tasks.filter((task) => task.status === "queued" || task.status === "blocked");
  const running = run.tasks.filter((task) => task.status === "running");
  const done = run.tasks.filter((task) => task.status === "done" || task.status === "failed");

  document.getElementById("queuedTasks").innerHTML = queued.map(renderTask).join("");
  document.getElementById("runningTasks").innerHTML = running.map(renderTask).join("");
  document.getElementById("doneTasks").innerHTML = done.map(renderTask).join("");

  document.getElementById("artifacts").innerHTML = run.artifacts.length
    ? run.artifacts
        .map(
          (artifact) => `
          <article class="artifact">
            <h3>${artifact.title}</h3>
            <pre>${artifact.content}</pre>
          </article>
        `,
        )
        .join("")
    : "<p class='muted'>Artifacts will appear once downstream tasks complete.</p>";

  document.getElementById("evidence").innerHTML = run.evidence.length
    ? run.evidence
        .map(
          (item) => `
          <article class="evidence-item">
            <h3>${item.title}</h3>
            <p><strong>Source:</strong> ${item.source_uri}</p>
            <p>${item.excerpt}</p>
          </article>
        `,
        )
        .join("")
    : "<p class='muted'>Evidence will populate as agents complete their tasks.</p>";
}

function renderTask(task) {
  return `<li><strong>${task.agent_name}</strong><br />${task.title}<br /><span class="muted">${task.status}</span></li>`;
}

async function refreshRuns() {
  const runs = await api("/api/runs");
  const selector = document.getElementById("runSelector");
  selector.innerHTML = runs
    .map((run) => `<option value="${run.id}" ${run.id === state.currentRunId ? "selected" : ""}>${run.area} — ${run.status}</option>`)
    .join("");
  if (!state.currentRunId && runs[0]) {
    state.currentRunId = runs[0].id;
  }
  if (state.currentRunId) {
    await refreshCurrentRun();
  }
}

async function refreshCurrentRun() {
  if (!state.currentRunId) return;
  const run = await api(`/api/runs/${state.currentRunId}`);
  renderRun(run);
}

async function refreshKnowledge() {
  const query = document.getElementById("knowledgeQuery").value.trim();
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  const knowledge = await api(`/api/knowledge${suffix}`);
  document.getElementById("knowledgeAssets").innerHTML = knowledge
    .map(
      (asset) => `
        <article class="knowledge-item">
          <h3>${asset.title}</h3>
          <p><strong>Path:</strong> ${asset.source_path}</p>
          <p>${asset.summary}</p>
        </article>
      `,
    )
    .join("");
}

async function createRun() {
  const area = document.getElementById("areaInput").value.trim();
  const notes = document.getElementById("notesInput").value.trim();
  if (!area) {
    document.getElementById("createRunMessage").textContent = "Area is required.";
    return;
  }
  const idempotencyKey = `${area.toLowerCase().replace(/\s+/g, "-")}-${Date.now()}`;
  const run = await api("/api/runs", {
    method: "POST",
    body: JSON.stringify({ area, notes, idempotency_key: idempotencyKey }),
  });
  document.getElementById("createRunMessage").textContent = `Run ${run.id} created for ${run.area}.`;
  await refreshRuns();
}

async function processCurrentRun() {
  if (!state.currentRunId) return;
  await api(`/api/runs/${state.currentRunId}/process`, { method: "POST" });
  await refreshCurrentRun();
}

document.getElementById("createRunButton").addEventListener("click", () => createRun().catch(showError));
document.getElementById("refreshButton").addEventListener("click", () => refreshRuns().catch(showError));
document.getElementById("processButton").addEventListener("click", () => processCurrentRun().catch(showError));
document.getElementById("runSelector").addEventListener("change", (event) => {
  state.currentRunId = event.target.value;
  refreshCurrentRun().catch(showError);
});
document.getElementById("knowledgeQuery").addEventListener("input", () => refreshKnowledge().catch(showError));

function showError(error) {
  document.getElementById("createRunMessage").textContent = error.message;
}

async function bootstrap() {
  await refreshKnowledge();
  await refreshRuns();
  if (state.pollHandle) {
    clearInterval(state.pollHandle);
  }
  state.pollHandle = setInterval(() => {
    refreshRuns().catch(() => {});
  }, 3000);
}

bootstrap().catch(showError);
