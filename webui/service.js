const healthStatus = document.getElementById("healthStatus");
const runtimeMode = document.getElementById("runtimeMode");
const providerCount = document.getElementById("providerCount");
const defaultProxyState = document.getElementById("defaultProxyState");
const logCount = document.getElementById("logCount");
const serverUrl = document.getElementById("serverUrl");
const serviceLogList = document.getElementById("serviceLogList");
const logMeta = document.getElementById("logMeta");

async function api(path) {
  const response = await fetch(path);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

function renderLogs(entries) {
  if (!entries.length) {
    serviceLogList.innerHTML = `<div class="service-empty">还没有服务模式日志。等 Emby 插件或调试请求进来后，这里会自动刷新。</div>`;
    return;
  }
  serviceLogList.innerHTML = "";
  entries
    .slice()
    .reverse()
    .forEach((entry) => {
      const item = document.createElement("div");
      const levelClass = entry.level.toLowerCase();
      item.className = "service-log-item";
      item.innerHTML = `
        <div class="service-log-meta">
          <span>${entry.timestamp}</span>
          <span class="service-log-level ${levelClass}">${entry.level}</span>
          <span>${entry.source}</span>
        </div>
        <div>${entry.message}</div>
      `;
      serviceLogList.appendChild(item);
    });
}

async function refreshHealth() {
  const [health, runtime] = await Promise.all([
    api("/emby-api/v1/health"),
    api("/api/runtime"),
  ]);
  healthStatus.textContent = health.status === "ok" ? "运行中" : "异常";
  runtimeMode.textContent = runtime.modeOverride || "手动选择";
  providerCount.textContent = String(health.providerCount);
  defaultProxyState.textContent = health.defaultProxyConfigured ? "已配置" : "未配置";
  logCount.textContent = String(health.logCount);
  serverUrl.textContent = window.location.origin;
}

async function refreshLogs() {
  const data = await api("/emby-api/v1/logs/recent");
  logMeta.textContent = `共 ${data.entries.length} 条，页面每 3 秒自动刷新`;
  renderLogs(data.entries);
}

async function tick() {
  try {
    await refreshHealth();
    await refreshLogs();
  } catch (error) {
    healthStatus.textContent = "请求失败";
    logMeta.textContent = error.message;
  } finally {
    window.setTimeout(tick, 3000);
  }
}

tick();
