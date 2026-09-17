const state = {
  accounts: [],
  accountId: "",
  songs: [],
  uploads: [],
  selected: new Set(),
  current: null,
  settings: null,
  logs: [],
  socket: null,
  socketTimer: null,
  pollTimer: null,
  formMode: "edit",
  view: "task",
};

const elements = {};

for (const id of [
  "service-status", "socket-status", "task-status", "account-select", "account-form",
  "account-new", "account-copy", "account-delete", "queue-caption", "select-all",
  "select-failed", "refresh-songs", "start-run", "pause-run", "resume-run", "stop-run",
  "fresh-run", "metric-pending", "metric-success", "metric-skip", "metric-fail",
  "metric-step", "song-table", "queue-empty", "settings-form", "save-settings",
  "log-stream", "copy-logs", "open-logs", "open-screenshots", "toast",
  "open-login", "close-login",
  "upload-caption", "upload-count", "upload-limit", "upload-real-name",
  "upload-table", "upload-empty", "refresh-uploads", "start-upload",
]) {
  elements[id] = document.getElementById(id);
}

function renderView() {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `view-${state.view}`);
  });
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === state.view);
  });
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", { hour12: false });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof body === "object" && body.detail ? body.detail : `请求失败 ${response.status}`);
  return body;
}

function toast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.style.background = isError ? "#8f2222" : "#202a28";
  elements.toast.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => elements.toast.classList.remove("show"), 3600);
}

function setServiceStatus(ok) {
  elements["service-status"].textContent = ok ? "服务正常" : "服务未连接";
  elements["service-status"].className = `status-chip ${ok ? "is-live" : "is-offline"}`;
}

function setSocketStatus(ok) {
  elements["socket-status"].textContent = ok ? "日志流已连接" : "日志流重连中";
  elements["socket-status"].className = `status-chip ${ok ? "is-live" : "is-warn"}`;
}

function runningStatuses() {
  return new Set(["running", "paused", "stopping"]);
}

function isRunning() {
  return Boolean(state.current && runningStatuses().has(state.current.status));
}

function renderTaskStatus() {
  const chip = elements["task-status"];
  if (!state.current) {
    chip.textContent = "无任务";
    chip.className = "status-chip";
    return;
  }
  const labels = {
    running: "任务运行中",
    paused: "已暂停",
    stopping: "正在停止",
    completed: "任务完成",
    failed: "任务失败",
    stopped: "已停止",
    generation_limit: "生成上限",
    login_required: "需要登录",
    verification_failed: "详情校验失败",
  };
  chip.textContent = labels[state.current.status] || state.current.status;
  chip.className = `status-chip ${runningStatuses().has(state.current.status) ? "is-active" : state.current.status === "completed" ? "is-live" : "is-warn"}`;
}

function renderAccounts() {
  const select = elements["account-select"];
  select.innerHTML = "";
  const option = new Option(state.accounts.length ? "选择账号" : "暂无账号", "");
  option.disabled = true;
  select.append(option);
  for (const account of state.accounts) {
    select.append(new Option(`${account.account_name} · ${account.chrome_debug_port}`, account.id));
  }
  select.value = state.accountId || "";
}

function fillAccountForm(account = null) {
  const form = elements["account-form"];
  const values = account || {
    account_name: "",
    chrome_profile_dir: "",
    chrome_debug_port: 9222,
    lyric_dir: "",
    output_dir: "",
    download_dir: "",
    model_name: "Sway v5.5",
    singer_name: "老岩",
    max_retries: 3,
    generation_batch_size: 2,
    upload_batch_size: 10,
    upload_artist_name: "白日逐梦",
    upload_real_name: "龙英",
    song_interval_seconds: 5,
    create_url: "https://music.douyin.com/studio/create",
  };
  form.reset();
  for (const [key, value] of Object.entries(values)) {
    if (form.elements[key]) form.elements[key].value = value;
  }
  state.formMode = account ? "edit" : "create";
}

function accountPayload() {
  const form = elements["account-form"];
  const payload = {
    account_name: form.account_name.value.trim(),
    chrome_profile_dir: form.chrome_profile_dir.value.trim(),
    chrome_debug_port: Number(form.chrome_debug_port.value),
    lyric_dir: form.lyric_dir.value.trim(),
    output_dir: form.output_dir.value.trim(),
    download_dir: form.download_dir.value.trim(),
    model_name: form.model_name.value.trim(),
    singer_name: form.singer_name.value.trim(),
    max_retries: Number(form.max_retries.value),
    generation_batch_size: Number(form.generation_batch_size.value),
    upload_batch_size: Number(form.upload_batch_size.value),
    upload_artist_name: form.upload_artist_name.value.trim(),
    upload_real_name: form.upload_real_name.value.trim(),
    song_interval_seconds: Number(form.song_interval_seconds.value),
    create_url: form.create_url.value.trim(),
    assets_url: "https://music.douyin.com/studio/assets",
  };
  if (!payload.account_name || !payload.chrome_profile_dir || !payload.lyric_dir || !payload.output_dir || !payload.download_dir) {
    throw new Error("请完整填写账号名称和四个目录路径");
  }
  return payload;
}

function formatSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function renderUploads() {
  const files = state.uploads?.files || [];
  elements["upload-table"].querySelectorAll(".upload-row:not(.upload-head)").forEach((node) => node.remove());
  elements["upload-empty"].classList.toggle("is-hidden", files.length > 0);
  elements["upload-count"].textContent = String(files.length);
  elements["upload-limit"].textContent = String(state.uploads?.batch_size || 10);
  elements["upload-real-name"].textContent = state.uploads?.real_name || "-";
  elements["upload-caption"].textContent = state.uploads?.day
    ? `${state.uploads.day} · ${files.length} 首可发布`
    : "等待成品下载完成";

  for (const file of files) {
    const row = document.createElement("div");
    row.className = "upload-row";
    const name = document.createElement("span");
    name.textContent = file.file_name;
    name.title = file.path;
    const size = document.createElement("span");
    size.textContent = formatSize(file.size);
    const status = document.createElement("span");
    status.innerHTML = '<span class="state state-waiting">待发布</span>';
    row.append(name, size, status);
    elements["upload-table"].append(row);
  }
}

function stateLabel(value) {
  const labels = {
    pending: "待处理", running: "处理中", success: "成功", failed: "失败",
    skipped: "已跳过", generation_limit: "生成上限", 解析失败: "解析失败",
  };
  return labels[value] || value || "待处理";
}

function songState(song) {
  if (!state.current) return song.valid ? "pending" : "解析失败";
  const match = state.current.songs.find((item) => item.file_name === song.file_name);
  return match ? match.status : song.valid ? "pending" : "解析失败";
}

function renderSongs() {
  const table = elements["song-table"];
  table.querySelectorAll(".song-row:not(.song-head)").forEach((node) => node.remove());
  elements["queue-empty"].classList.toggle("is-hidden", state.songs.length > 0);
  elements["queue-empty"].querySelector("strong").textContent = state.accounts.length ? "暂无歌词" : "请先创建账号";

  for (const song of state.songs) {
    const row = document.createElement("label");
    row.className = "song-row";
    const status = songState(song);
    const progress = state.current?.songs.find((item) => item.file_name === song.file_name);
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selected.has(song.file_name);
    checkbox.disabled = isRunning() || !song.valid;
    checkbox.dataset.file = song.file_name;
    row.append(checkbox);
    for (const text of [song.file_name, song.song_name || (song.valid ? "-" : "解析失败")]) {
      const span = document.createElement("span");
      span.textContent = text;
      row.append(span);
    }
    const stateSpan = document.createElement("span");
    stateSpan.innerHTML = `<span class="state state-${status}">${stateLabel(status)}</span>`;
    row.append(stateSpan);
    const step = document.createElement("span");
    step.textContent = progress?.current_step || (song.error ? "解析" : "-");
    step.title = song.error || progress?.error || "";
    row.append(step);
    const retry = document.createElement("span");
    retry.textContent = progress?.attempts || 0;
    row.append(retry);
    table.append(row);
  }

  table.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selected.add(checkbox.dataset.file);
      else state.selected.delete(checkbox.dataset.file);
      renderMetrics();
    });
  });
  renderMetrics();
}

function renderMetrics() {
  const current = state.current;
  const running = state.songs.filter((song) => songState(song) === "pending" || songState(song) === "running").length;
  elements["metric-pending"].textContent = String(running);
  elements["metric-success"].textContent = String(current?.success_count || 0);
  elements["metric-skip"].textContent = String(current?.skipped_count || 0);
  elements["metric-fail"].textContent = String(current?.failure_count || 0);
  elements["metric-step"].textContent = current?.current_step || "-";
}

function renderControls() {
  const running = isRunning();
  for (const id of ["account-new", "account-copy", "account-delete", "select-all", "select-failed", "refresh-songs", "start-run"]) {
    elements[id].disabled = running;
  }
  elements["pause-run"].disabled = !running || state.current?.status !== "running";
  elements["resume-run"].disabled = !running || state.current?.status !== "paused";
  elements["stop-run"].disabled = !running;
  elements["fresh-run"].disabled = running;
  elements["account-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  elements["settings-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  elements["save-settings"].disabled = running;
  elements["open-login"].disabled = running || !state.accountId;
  elements["close-login"].disabled = running;
}

function appendLog(entry) {
  state.logs.push(entry);
  if (state.logs.length > 1000) state.logs.splice(0, state.logs.length - 1000);
  const line = document.createElement("div");
  line.className = `log-line log-level-${entry.level}`;
  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = formatTime(entry.timestamp);
  const step = document.createElement("span");
  step.className = "log-step";
  step.textContent = entry.step;
  const message = document.createElement("span");
  message.className = "log-message";
  message.textContent = `${entry.song ? `[${entry.song}] ` : ""}${entry.message}${entry.screenshot_path ? ` 截图: ${entry.screenshot_path}` : ""}`;
  line.append(time, step, message);
  elements["log-stream"].append(line);
  while (elements["log-stream"].childElementCount > 1000) elements["log-stream"].firstElementChild.remove();
  elements["log-stream"].scrollTop = elements["log-stream"].scrollHeight;
}

function renderCurrent() {
  renderTaskStatus();
  renderSongs();
  renderControls();
}

async function loadHealth() {
  try {
    await api("/api/health");
    setServiceStatus(true);
  } catch {
    setServiceStatus(false);
  }
}

async function loadAccounts(selectId = null) {
  state.accounts = await api("/api/accounts");
  const previous = selectId || state.accountId || state.accounts[0]?.id || "";
  state.accountId = state.accounts.some((account) => account.id === previous) ? previous : "";
  renderAccounts();
  const account = state.accounts.find((item) => item.id === state.accountId);
  fillAccountForm(account);
  if (account) await loadSongs();
  else state.songs = [];
  await loadUploads();
  renderSongs();
  renderControls();
}

async function loadSongs() {
  if (!state.accountId) return;
  const account = state.accounts.find((item) => item.id === state.accountId);
  state.songs = await api(`/api/accounts/${state.accountId}/songs`);
  state.selected = new Set(state.songs.filter((song) => song.valid).map((song) => song.file_name));
  elements["queue-caption"].textContent = `${account.account_name} · ${state.songs.length} 个文件`;
  renderSongs();
}

async function loadUploads() {
  if (!state.accountId) {
    state.uploads = [];
    renderUploads();
    return;
  }
  try {
    state.uploads = await api(`/api/accounts/${state.accountId}/uploads`);
  } catch {
    state.uploads = [];
  }
  renderUploads();
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  const form = elements["settings-form"];
  for (const key of Object.keys(state.settings)) {
    if (form.elements[key]) form.elements[key].value = state.settings[key];
  }
}

async function loadCurrent() {
  state.current = await api("/api/runs/current");
  renderCurrent();
}

async function loadLoginBrowser() {
  const current = await api("/api/browser/current").catch(() => null);
  elements["close-login"].textContent = current
    ? `关闭 ${current.account_name} 浏览器`
    : "关闭登录浏览器";
}

function connectSocket() {
  if (state.socket) state.socket.close();
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws`);
  state.socket = socket;
  socket.addEventListener("open", () => {
    setSocketStatus(true);
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "log") appendLog(message.data);
    if (message.type === "status") {
      state.current = message.data;
      renderCurrent();
    }
  });
  socket.addEventListener("close", () => {
    setSocketStatus(false);
    state.socket = null;
    if (!state.pollTimer) state.pollTimer = setInterval(loadCurrent, 3000);
    clearTimeout(state.socketTimer);
    state.socketTimer = setTimeout(connectSocket, 2500);
  });
  socket.addEventListener("error", () => socket.close());
}

async function runControl(action) {
  try {
    state.current = await api("/api/runs/control", { method: "POST", body: JSON.stringify({ action }) });
    renderCurrent();
    toast(action === "pause" ? "已请求暂停" : action === "resume" ? "已继续" : "已请求停止");
  } catch (error) {
    toast(error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  setupTooltips();
  bindEvents();
  renderView();
  await Promise.allSettled([loadHealth(), loadSettings(), loadCurrent()]);
  await loadAccounts();
  await loadUploads();
  await loadLoginBrowser();
  const recent = await api("/api/logs/recent").catch(() => []);
  for (const event of recent) if (event.type === "log") appendLog(event.data);
  connectSocket();
  setInterval(loadHealth, 5000);
  setInterval(loadLoginBrowser, 5000);
  setInterval(loadUploads, 10000);
});

function setupTooltips() {
  const tooltip = document.getElementById("floating-tooltip");
  let currentTarget = null;

  function show(target, event) {
    const text = target.getAttribute("data-tip");
    if (!text) return;
    currentTarget = target;
    tooltip.textContent = text;
    tooltip.classList.add("show");
    tooltip.setAttribute("aria-hidden", "false");
    position(event instanceof PointerEvent ? event : null, target);
  }

  function position(event, target) {
    const rect = target.getBoundingClientRect();
    const point = event ?? { clientX: rect.left + rect.width / 2, clientY: rect.bottom };
    tooltip.style.left = "0px";
    tooltip.style.top = "0px";
    const box = tooltip.getBoundingClientRect();
    const padding = 10;
    let x = point.clientX + 12;
    let y = point.clientY + 14;
    if (x + box.width + padding > window.innerWidth) x = window.innerWidth - box.width - padding;
    if (y + box.height + padding > window.innerHeight) y = point.clientY - box.height - 12;
    x = Math.max(padding, x);
    y = Math.max(padding, y);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }

  function hide() {
    currentTarget = null;
    tooltip.classList.remove("show");
    tooltip.setAttribute("aria-hidden", "true");
  }

  document.addEventListener("pointerover", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target) show(target, event);
  });
  document.addEventListener("pointermove", (event) => {
    if (currentTarget) position(event, currentTarget);
  }, { passive: true });
  document.addEventListener("pointerout", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target && target === currentTarget) hide();
  });
  document.addEventListener("focusin", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target) show(target, null);
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  window.addEventListener("scroll", hide, { passive: true });
}

function bindEvents() {
  document.querySelectorAll(".nav-item:not(.is-disabled)").forEach((item) => {
    item.addEventListener("click", () => {
      state.view = item.dataset.view;
      renderView();
    });
  });

  elements["account-select"].addEventListener("change", async () => {
    state.accountId = elements["account-select"].value;
    fillAccountForm(state.accounts.find((account) => account.id === state.accountId));
    renderControls();
    await loadSongs();
    await loadUploads();
  });

  elements["account-new"].addEventListener("click", () => {
    state.accountId = "";
    renderAccounts();
    fillAccountForm();
    elements["account-form"].account_name.focus();
  });

  elements["account-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = accountPayload();
      if (state.formMode === "create") {
        const account = await api("/api/accounts", { method: "POST", body: JSON.stringify(payload) });
        await loadAccounts(account.id);
        toast("账号已创建");
      } else {
        await api(`/api/accounts/${state.accountId}`, { method: "PUT", body: JSON.stringify(payload) });
        await loadAccounts(state.accountId);
        toast("账号已保存");
      }
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["account-copy"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    const account = state.accounts.find((item) => item.id === state.accountId);
    const name = `${account.account_name}-副本`;
    try {
      const copied = await api(`/api/accounts/${state.accountId}/copy`, { method: "POST", body: JSON.stringify({ account_name: name }) });
      await loadAccounts(copied.id);
      toast("账号已复制");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["account-delete"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    if (!confirm("删除控制台里的账号配置？不会删除 Chrome 目录和音乐文件。")) return;
    try {
      await api(`/api/accounts/${state.accountId}`, { method: "DELETE" });
      await loadAccounts();
      toast("账号配置已删除");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["refresh-songs"].addEventListener("click", async () => {
    try { await loadSongs(); toast("歌词列表已刷新"); } catch (error) { toast(error.message, true); }
  });
  elements["refresh-uploads"].addEventListener("click", async () => {
    try {
      await loadUploads();
      toast("上传批次已刷新");
    } catch (error) {
      toast(error.message, true);
    }
  });
  elements["select-all"].addEventListener("click", () => {
    state.selected = new Set(state.songs.filter((song) => song.valid).map((song) => song.file_name));
    renderSongs();
  });
  elements["select-failed"].addEventListener("click", () => {
    state.selected = new Set(state.songs.filter((song) => !song.valid || songState(song) === "failed").map((song) => song.file_name));
    renderSongs();
  });

  elements["start-run"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    if (!state.selected.size) return toast("请选择歌词文件", true);
    try {
      state.current = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          account_id: state.accountId,
          song_files: [...state.selected],
          fresh_run: elements["fresh-run"].checked,
        }),
      });
      renderCurrent();
      toast("任务已启动");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["pause-run"].addEventListener("click", () => runControl("pause"));
  elements["resume-run"].addEventListener("click", () => runControl("resume"));
  elements["stop-run"].addEventListener("click", () => runControl("stop"));

  elements["settings-form"].addEventListener("submit", (event) => event.preventDefault());
  elements["save-settings"].addEventListener("click", async () => {
    const form = elements["settings-form"];
    const payload = {};
    for (const input of form.elements) payload[input.name] = Number(input.value);
    try {
      state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      await loadSettings();
      toast("运行参数已保存");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["copy-logs"].addEventListener("click", async () => {
    const text = state.logs.map((entry) => `${formatTime(entry.timestamp)} ${entry.step} ${entry.message}`).join("\n");
    await navigator.clipboard.writeText(text);
    toast("日志已复制");
  });
  elements["open-logs"].addEventListener("click", () => openFolder("logs"));
  elements["open-screenshots"].addEventListener("click", () => openFolder("screenshots"));
  elements["open-login"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    try {
      const result = await api(`/api/accounts/${state.accountId}/browser/open`, { method: "POST" });
      await loadLoginBrowser();
      toast(`已打开 ${result.account_name} 的 Chrome，请登录后关闭浏览器`);
    } catch (error) {
      toast(error.message, true);
    }
  });
  elements["close-login"].addEventListener("click", async () => {
    try {
      await api("/api/browser/close", { method: "POST" });
      await loadLoginBrowser();
      toast("登录浏览器已关闭");
    } catch (error) {
      toast(error.message, true);
    }
  });
}

async function openFolder(kind) {
  try {
    await api("/api/folders/open", { method: "POST", body: JSON.stringify({ kind }) });
    toast("已打开目录");
  } catch (error) {
    toast(error.message, true);
  }
}
