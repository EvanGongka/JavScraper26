const state = {
  providers: [],
  entries: [],
  taskId: null,
  logCount: 0,
  proxy: {
    enabled: false,
    protocol: "http",
    host: "",
    port: "",
  },
  connectivityResolved: null,
};

const sourcePath = document.getElementById("sourcePath");
const outputPath = document.getElementById("outputPath");
const providerList = document.getElementById("providerList");
const resultBody = document.getElementById("resultBody");
const logOutput = document.getElementById("logOutput");
const scanSummary = document.getElementById("scanSummary");
const taskSummary = document.getElementById("taskSummary");
const connectivityModal = document.getElementById("connectivityModal");
const connectivityResults = document.getElementById("connectivityResults");
const connectivitySummary = document.getElementById("connectivitySummary");
const proxyEnabled = document.getElementById("proxyEnabled");
const proxyProtocol = document.getElementById("proxyProtocol");
const proxyHost = document.getElementById("proxyHost");
const proxyPort = document.getElementById("proxyPort");
const selectAllProvidersButton = document.getElementById("selectAllProviders");
const clearAllProvidersButton = document.getElementById("clearAllProviders");

function renderProviders() {
  providerList.innerHTML = "";
  let currentGroup = "";
  state.providers.forEach((provider, index) => {
    if (provider.group !== currentGroup) {
      currentGroup = provider.group;
      const groupItem = document.createElement("li");
      groupItem.className = "provider-group";
      groupItem.innerHTML = `
        <div class="provider-group-title">${provider.groupLabel}</div>
        <div class="provider-group-tip">${
          provider.group === "regular"
            ? "优先尝试普通番号站点，先用原生竖图，拿不到再裁切"
            : "特殊番号站点默认三图同源，顺序固定在普通站点之后"
        }</div>
      `;
      providerList.appendChild(groupItem);
    }
    const previous = state.providers[index - 1];
    const next = state.providers[index + 1];
    const canMoveUp = previous && previous.group === provider.group;
    const canMoveDown = next && next.group === provider.group;
    const hint = provider.requiresLogin
      ? `<div class="hint-text warn">${provider.hint || "需要浏览器登录态，默认放在最后"}</div>`
      : `<div class="hint-text">按顺序依次刮削，命中后立即停止后续站点</div>`;
    const li = document.createElement("li");
    li.className = "provider-item";
    li.innerHTML = `
      <input type="checkbox" ${provider.enabled ? "checked" : ""} data-index="${index}" class="provider-toggle" />
      <div>
        <strong>${provider.name}</strong>
        ${hint}
      </div>
      <div class="provider-actions">
        <button data-move="up" data-index="${index}" ${canMoveUp ? "" : "disabled"}>上移</button>
        <button data-move="down" data-index="${index}" ${canMoveDown ? "" : "disabled"}>下移</button>
      </div>
    `;
    providerList.appendChild(li);
  });

  providerList.querySelectorAll(".provider-toggle").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const index = Number(event.target.dataset.index);
      state.providers[index].enabled = event.target.checked;
    });
  });

  providerList.querySelectorAll("[data-move]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.index);
      const direction = button.dataset.move;
      const target = direction === "up" ? index - 1 : index + 1;
      if (target < 0 || target >= state.providers.length) return;
      if (state.providers[index].group !== state.providers[target].group) return;
      [state.providers[index], state.providers[target]] = [state.providers[target], state.providers[index]];
      renderProviders();
    });
  });
}

function selectedProviders() {
  return state.providers.filter((item) => item.enabled).map((item) => item.name);
}

function setAllProvidersEnabled(enabled) {
  state.providers = state.providers.map((provider) => ({
    ...provider,
    enabled,
  }));
  renderProviders();
}

function renderEntries() {
  resultBody.innerHTML = "";
  if (!state.entries.length) {
    resultBody.innerHTML = `<tr><td colspan="4" style="color: var(--muted);">还没有扫描结果</td></tr>`;
    return;
  }

  state.entries.forEach((entry) => {
    const tr = document.createElement("tr");
    const failed = entry.status === "失败";
    tr.innerHTML = `
      <td>${entry.code}</td>
      <td>${entry.fileCount}</td>
      <td><span class="cell-wrap">${entry.primaryFile}</span></td>
      <td><span class="status-pill ${failed ? "failed" : ""}">${entry.status}</span></td>
    `;
    resultBody.appendChild(tr);
  });
}

function appendLogs(logs) {
  if (!logs.length) return;
  const newLogs = logs.slice(state.logCount);
  if (!newLogs.length) return;
  logOutput.textContent += (logOutput.textContent ? "\n" : "") + newLogs.join("\n");
  logOutput.scrollTop = logOutput.scrollHeight;
  state.logCount = logs.length;
}

function syncStatuses(taskEntries) {
  state.entries = state.entries.map((entry) => ({
    ...entry,
    status: taskEntries[entry.code] || entry.status,
  }));
  renderEntries();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

async function pickDirectory(title, input) {
  try {
    const data = await api("/api/pick-directory", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    input.value = data.path;
    if (input === sourcePath && !outputPath.value) {
      outputPath.value = `${data.path}/javScraper26-output`;
    }
  } catch (error) {
    window.alert(error.message);
  }
}

async function scan() {
  if (!sourcePath.value.trim()) {
    window.alert("请先选择扫描目录");
    return;
  }
  scanSummary.textContent = "正在扫描...";
  try {
    const data = await api("/api/scan", {
      method: "POST",
      body: JSON.stringify({ sourcePath: sourcePath.value.trim() }),
    });
    state.entries = data.entries.map((entry) => ({ ...entry }));
    renderEntries();
    scanSummary.textContent = `识别到 ${data.entries.length} 条，跳过 ${data.skipped.length} 个文件`;
    if (data.skipped.length) {
      logOutput.textContent = `跳过文件：\n${data.skipped.join("\n")}`;
      state.logCount = 0;
    } else {
      logOutput.textContent = "";
      state.logCount = 0;
    }
  } catch (error) {
    scanSummary.textContent = "扫描失败";
    window.alert(error.message);
  }
}

function currentProxyPayload() {
  return {
    enabled: proxyEnabled.checked,
    protocol: proxyProtocol.value,
    host: proxyHost.value.trim(),
    port: proxyPort.value.trim(),
  };
}

function openConnectivityModal() {
  connectivityModal.classList.remove("hidden");
}

function closeConnectivityModal() {
  connectivityModal.classList.add("hidden");
}

function updateConnectivitySummary(results) {
  const completed = results.filter((item) => item.state !== "loading");
  const failedCount = completed.filter((item) => item.ok === false).length;
  const loadingCount = results.filter((item) => item.state === "loading").length;
  if (loadingCount > 0) {
    connectivitySummary.textContent = `正在校验 ${results.length} 个站点，剩余 ${loadingCount} 个...`;
    return;
  }
  connectivitySummary.textContent =
    failedCount === 0
      ? "当前勾选站点都可访问，可以继续刮削。"
      : `当前勾选站点里有 ${failedCount} 个暂时不可访问。你可以填写代理后重新校验，或者启用全局代理 / TUN 模式。`;
}

function renderConnectivity(results) {
  updateConnectivitySummary(results);
  connectivityResults.innerHTML = "";
  results.forEach((item) => {
    const stateClass = item.state === "loading" ? "loading" : item.ok ? "" : "failed";
    const stateText = item.state === "loading" ? "校验中" : item.ok ? "可访问" : "不可访问";
    const detailText = item.state === "loading" ? "正在发起请求，请稍候..." : item.detail;
    const div = document.createElement("div");
    div.className = `connectivity-item ${stateClass}`;
    div.innerHTML = `
      <strong>${item.name}</strong>
      <span class="status-pill ${stateClass}">${item.state === "loading" ? '<span class="loading-dot"></span>' : ""}${stateText}</span>
      <div>
        <div>${detailText}</div>
        <div style="color: var(--muted); font-size: 12px; margin-top: 6px;">${item.finalUrl || item.url}</div>
      </div>
    `;
    connectivityResults.appendChild(div);
  });
}

async function checkConnectivityProgressive(providerNames = selectedProviders()) {
  if (!providerNames.length) {
    window.alert("请至少启用一个站点");
    return [];
  }
  const proxy = currentProxyPayload();
  const results = providerNames.map((name) => ({
    name,
    url: "",
    ok: null,
    status: null,
    detail: "",
    finalUrl: "",
    state: "loading",
  }));
  renderConnectivity(results);

  try {
    const data = await api("/api/connectivity", {
      method: "POST",
      body: JSON.stringify({ proxy, sites: providerNames }),
    });
    data.results.forEach((item, index) => {
      Object.assign(results[index], item, { state: "done" });
    });
  } catch (error) {
    results.forEach((item) => {
      Object.assign(item, {
        ok: false,
        status: null,
        detail: error.message,
        finalUrl: item.url,
        state: "done",
      });
    });
  }

  renderConnectivity(results);

  return results;
}

async function ensureScanned() {
  if (state.entries.length) {
    return true;
  }
  if (!sourcePath.value.trim()) {
    window.alert("请先选择扫描目录");
    return false;
  }
  await scan();
  return state.entries.length > 0;
}

async function pollTask() {
  if (!state.taskId) return;
  const data = await api(`/api/tasks/${state.taskId}`);
  appendLogs(data.logs);
  syncStatuses(data.entries);
  taskSummary.textContent = `${data.status}${data.manifestPath ? ` · ${data.manifestPath}` : ""}`;
  if (data.status === "running") {
    window.setTimeout(pollTask, 1200);
    return;
  }
  if (data.status === "failed") {
    state.taskId = null;
    window.alert(data.error || "任务失败");
    return;
  }
  state.taskId = null;
  const failedCodes = state.entries.filter((entry) => entry.status === "失败").map((entry) => entry.code);
  const successCount = state.entries.length - failedCodes.length;
  const failureText = failedCodes.length
    ? `\n未成功条目（${failedCodes.length}）：\n${failedCodes.join("\n")}`
    : "\n全部条目都已抓取成功。";
  window.alert(`刮削完成。\n成功 ${successCount} 条，失败 ${failedCodes.length} 条。${failureText}`);
}

async function startTask() {
  const ready = await ensureScanned();
  if (!ready) {
    return;
  }
  if (!outputPath.value.trim()) {
    window.alert("请先选择输出目录");
    return;
  }
  const providers = selectedProviders();
  if (!providers.length) {
    window.alert("请至少启用一个站点");
    return;
  }

  openConnectivityModal();
  try {
    const results = await checkConnectivityProgressive(providers);
    await new Promise((resolve, reject) => {
      state.connectivityResolved = { resolve, reject, results, providers };
    });
  } catch (error) {
    if (error.message === "已取消刮削") {
      taskSummary.textContent = "已取消";
      return;
    }
    closeConnectivityModal();
    window.alert(error.message);
    return;
  }

  logOutput.textContent = "";
  state.logCount = 0;
  taskSummary.textContent = "任务启动中...";

  try {
    const data = await api("/api/start", {
      method: "POST",
      body: JSON.stringify({
        sourcePath: sourcePath.value.trim(),
        outputPath: outputPath.value.trim(),
        providers,
        proxy: currentProxyPayload(),
      }),
    });
    state.taskId = data.taskId;
    pollTask();
  } catch (error) {
    taskSummary.textContent = "任务启动失败";
    window.alert(error.message);
  }
}

async function bootstrap() {
  const data = await api("/api/providers");
  state.providers = data.providers.map((item) => ({
    ...item,
    enabled: item.defaultEnabled !== false,
  }));
  renderProviders();
  renderEntries();
}

document.getElementById("pickSource").addEventListener("click", () => pickDirectory("选择扫描目录", sourcePath));
document.getElementById("pickOutput").addEventListener("click", () => pickDirectory("选择输出目录", outputPath));
document.getElementById("scanButton").addEventListener("click", scan);
document.getElementById("startButton").addEventListener("click", startTask);
document.getElementById("closeConnectivityModal").addEventListener("click", () => {
  if (state.connectivityResolved) {
    state.connectivityResolved.reject(new Error("已取消刮削"));
    state.connectivityResolved = null;
  }
  closeConnectivityModal();
});
document.getElementById("recheckConnectivity").addEventListener("click", async () => {
  try {
    const providers = state.connectivityResolved?.providers || selectedProviders();
    await checkConnectivityProgressive(providers);
  } catch (error) {
    window.alert(error.message);
  }
});
document.getElementById("continueAfterConnectivity").addEventListener("click", () => {
  if (state.connectivityResolved) {
    state.connectivityResolved.resolve(true);
    state.connectivityResolved = null;
  }
  closeConnectivityModal();
});

if (selectAllProvidersButton) {
  selectAllProvidersButton.addEventListener("click", () => {
    setAllProvidersEnabled(true);
  });
}

if (clearAllProvidersButton) {
  clearAllProvidersButton.addEventListener("click", () => {
    setAllProvidersEnabled(false);
  });
}

bootstrap().catch((error) => {
  window.alert(error.message);
});
