const state = {
  accounts: [],
  accountId: "",
  songs: [],
  uploads: [],
  selected: new Set(),
  selectedUploads: new Set(),
  uploadSelectionTouched: false,
  uploadSelectionAccountId: "",
  uploadAiCreated: true,
  uploadContractSavingIds: new Set(),
  autoReplaceNoncompliant: true,
  pipelineRun: null,
  pipelineSyncedSignature: "",
  pipelineQueue: null,
  pipelineQueueOptions: [],
  pipelineQueueOrder: [],
  selectedPipelineQueueAccounts: new Set(),
  selectedPipelineDetailAccountId: "",
  pipelineDetailPinned: false,
  selectedTaskAccounts: new Set(),
  multiQueue: null,
  latestLyricQueue: null,
  dashboardSongs: {},
  generationRuns: {},
  uploadRuns: {},
  accountTemplates: {},
  stageUploads: {},
  lyricTemplateAccountLocked: false,
  editingStageAccountId: "",
  current: null,
  runStatus: "",
  notifiedRunId: "",
  settings: null,
  logs: [],
  socket: null,
  socketTimer: null,
  pollTimer: null,
  formMode: "edit",
  view: "dashboard",
  stage: "generation",
  generationModel: "自动",
  generationSinger: "",
  settingsTab: "runtime",
  accountReloadId: 0,
  accountRoot: "",
  aiConfigEditorOpen: false,
  editingAIProviderId: "",
  aiApiChecks: {},
  accountEditorOpen: false,
  editingAccountId: "",
  loginBrowser: null,
  lyricTemplates: [],
  lyricSystemPrompt: "",
  lyricResults: [],
  lyricGenerating: false,
  lyricProgress: null,
  lyricProgressStartedAt: 0,
  lyricProgressTimer: null,
  lyricPromptSaving: false,
  lyricPromptDirty: false,
  lyricTemplateEditorOpen: false,
  editingLyricTemplateId: "",
  selectedTemplateThemes: [],
  selectedLyricTemplateId: "",
  monitoringStatistics: null,
  monitoringLoading: false,
  monitoringSettings: null,
  monitoringSelectedAccountIds: new Set(),
  monitoringViewAccountId: "all",
  monitoringCollection: null,
  monitoringCollectionLoading: false,
  monitoringCollectionRequestSeq: 0,
};

const UPLOAD_CONTRACT_MODE_LABELS = {
  exclusive_agent: "独家代理发行",
  exclusive_authorization: "独家授权",
};
const UPLOAD_CONTRACT_MODES = [
  { value: "exclusive_agent", label: "独家代理发行" },
  { value: "exclusive_authorization", label: "独家授权" },
];

const THEME_OPTIONS = ["爱情", "友情", "校园", "都市", "治愈", "励志", "古风", "家庭", "旅行", "孤独"];
const DEFAULT_CREATE_URL = "https://music.douyin.com/studio/create";
const SWAY_MODEL_NAME = "Sway v5.5";
const GENERATION_MODEL_STORAGE_KEY = "aimusic.generationModel";
const GENERATION_SINGER_STORAGE_KEY = "aimusic.generationSinger";

const elements = {};

for (const id of [
  "service-status", "socket-status", "task-status", "account-select", "account-form",
  "account-new", "account-cancel", "account-copy", "account-cards",
  "account-root-field", "account-root-input", "choose-account-root", "account-derived-paths",
  "derived-lyric-path", "derived-output-path", "derived-download-path", "derived-chrome-path",
  "chrome-profile-field", "lyric-dir-field", "output-dir-field", "download-dir-field",
  "queue-caption", "select-all",
  "generation-model", "generation-singer",
  "select-failed", "repair-run", "refresh-songs", "start-run", "pause-run", "resume-run", "stop-run",
  "fresh-run", "metric-pending", "metric-success", "metric-skip", "metric-fail",
  "metric-step", "song-table", "queue-empty", "settings-form", "save-settings",
  "ai-settings-form", "settings-subnav", "settings-tab-runtime", "settings-tab-ai", "settings-tab-prompt", "test-ai-settings",
  "ai-config-cards", "ai-config-cancel",
  "lyric-dir-input", "current-lyric-folder", "apply-lyric-dir",
  "pipeline-caption", "pipeline-ai-created",
  "pipeline-rejected-action",
  "pipeline-model", "pipeline-singer",
  "pipeline-pause", "pipeline-start", "pipeline-resume", "pipeline-stop", "pipeline-stage-strip",
  "pipeline-refresh", "pipeline-queue-list", "pipeline-queue-caption", "pipeline-queue-table",
  "pipeline-phase-summary",
  "pipeline-table", "pipeline-empty",
  "log-stream", "copy-logs", "open-logs", "open-screenshots", "toast",
  "upload-caption", "upload-count", "upload-limit",
  "upload-table", "upload-empty", "refresh-uploads", "start-upload",
  "retry-uploads",
  "select-all-uploads", "clear-upload-selection",
  "upload-dir-input", "current-upload-folder", "apply-upload-dir",
  "upload-ai-created",
  "upload-rejected-action",
  "external-verification-note", "stop-upload",
  "retry-rejected-upload",
  "workflow-header", "stage-lyrics", "stage-generation", "stage-upload", "stage-pipeline",
  "task-account-all", "task-account-clear", "task-account-list", "task-account-count",
  "stage-account-table", "workflow-title", "workflow-caption", "ai-provider-select",
  "multi-stage-caption", "multi-lyrics-start", "workflow-date",
  "generation-account-form", "generation-account-title", "generation-account-cancel",
  "account-model-select", "account-singer-select",
  "dashboard-date", "dashboard-account-count", "dashboard-lyric-count", "dashboard-download-count",
  "dashboard-pending-upload-count", "dashboard-published-count", "dashboard-error-count", "dashboard-account-table",
  "lyric-summary-caption", "lyric-summary-list", "settings-template-slot",
  "lyric-system-prompt", "save-lyric-prompt", "lyric-results", "lyric-empty", "save-lyrics",
  "lyric-prompt-details", "lyric-prompt-panel",
  "lyric-progress-panel", "lyric-progress-message", "lyric-progress-elapsed", "lyric-progress-chars",
  "lyric-progress-count", "lyric-progress-names", "lyric-progress-reasoning",
  "lyric-result-caption",
  "lyric-template-caption", "lyric-template-cards", "lyric-template-form", "new-lyric-template",
  "template-account-select", "template-name", "template-lyric-tone", "template-song-style",
  "template-generation-count", "template-output-location",
  "template-theme-options", "custom-theme", "add-custom-theme", "save-lyric-template",
  "cancel-lyric-template",
  "monitoring-caption", "refresh-monitoring", "monitoring-account-count",
  "monitoring-collection-count", "monitoring-success-count", "monitoring-failed-count", "monitoring-table",
  "monitoring-empty", "monitoring-status-list",
  "collect-monitoring", "stop-monitoring", "monitoring-account-list", "monitoring-account-all",
  "monitoring-account-clear", "monitoring-view-list",
]) {
  elements[id] = document.getElementById(id);
}

function renderView() {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `view-${state.view}`);
  });
  const workflowVisible = state.view === "task" || state.view === "lyrics";
  document.body.classList.toggle("task-view-active", workflowVisible);
  elements["workflow-header"].hidden = !workflowVisible;
  document.querySelectorAll(".nav-item").forEach((item) => {
    const viewMatches = item.dataset.view === state.view;
    const stageMatches = item.dataset.view !== "task" || item.dataset.stage === state.stage;
    item.classList.toggle("is-active", viewMatches && stageMatches);
  });
  renderStages();
  renderTaskAccounts();
  renderDashboard();
  renderSettingsTabs();
  renderMonitoring();
}

function renderStages() {
  document.body.dataset.stage = state.stage;
  document.querySelectorAll(".stage").forEach((item) => {
    const active = item.dataset.stage === state.stage;
    item.classList.toggle("is-active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function syncLyricQueueSnapshot(queue) {
  if (queue?.stage === "lyrics" && queue.day === todayValue()) {
    state.latestLyricQueue = queue;
  }
  if (state.latestLyricQueue && state.latestLyricQueue.day !== todayValue()) {
    state.latestLyricQueue = null;
  }
}

function renderDashboard() {
  const day = todayValue();
  const lyricQueue = state.multiQueue?.stage === "lyrics" && state.multiQueue.day === day
    ? state.multiQueue
    : (state.latestLyricQueue?.day === day ? state.latestLyricQueue : null);
  const statuses = state.songs.map(songState);
  const files = state.uploads?.files || [];
  const uploadedFiles = state.uploads?.uploaded_files || [];
  const dailyUsed = Number(state.uploads?.daily_used ?? uploadedFiles.length);
  const successful = statuses.filter((status) => status === "success" || status === "skipped").length;
  const failed = statuses.filter(isFailureStatus).length;
  const lyricItems = lyricQueue?.items || [];
  const savedLyricCount = lyricItems.reduce(
    (total, item) => total + Number(item.result?.saved_count ?? item.result?.generated_count ?? 0),
    0,
  );
  const failedLyricAccounts = lyricItems.filter((item) => item.status === "failed").length;
  const dashboardSongsLoaded = state.accounts.every((account) => Object.hasOwn(state.dashboardSongs, account.id));
  const directoryLyricCount = dashboardSongsLoaded
    ? state.accounts.reduce((total, account) => total + (state.dashboardSongs[account.id] || []).length, 0)
    : state.songs.length;
  const lyricCount = Math.max(directoryLyricCount, lyricQueue ? savedLyricCount : 0);
  const errorCount = lyricQueue ? failedLyricAccounts : failed;

  elements["dashboard-date"].textContent = `今日 ${day}`;
  elements["workflow-date"].textContent = `日期 ${day}`;
  elements["dashboard-account-count"].textContent = String(state.accounts.length);
  elements["dashboard-lyric-count"].textContent = String(lyricCount);
  elements["dashboard-download-count"].textContent = String(successful);
  elements["dashboard-pending-upload-count"].textContent = String(files.length);
  elements["dashboard-published-count"].textContent = state.uploads ? String(dailyUsed) : "-";
  elements["dashboard-error-count"].textContent = String(errorCount);

  const table = elements["dashboard-account-table"];
  table.querySelectorAll(".dashboard-account-row:not(.dashboard-account-head)").forEach((node) => node.remove());

  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "dashboard-account-row dashboard-account-empty";
    empty.textContent = "暂无账号";
    table.append(empty);
    return;
  }

  const statusLabels = { pending: "等待", running: "处理中", completed: "成功", failed: "失败", stopped: "停止" };
  const statusQueue = state.multiQueue?.day === day ? state.multiQueue : lyricQueue;
  state.accounts.forEach((account) => {
    const lyricItem = lyricQueue?.items.find((item) => item.account_id === account.id);
    const queueItem = statusQueue?.items.find((item) => item.account_id === account.id);
    const isCurrent = account.id === state.accountId;
    const accountSongs = state.dashboardSongs[account.id] || [];
    const accountSongsLoaded = Object.hasOwn(state.dashboardSongs, account.id);
    const accountLyricCount = lyricItem
      ? Number(lyricItem.result?.saved_count ?? lyricItem.result?.generated_count ?? 0)
      : accountSongsLoaded ? accountSongs.length : isCurrent ? state.songs.length : 0;
    const row = document.createElement("div");
    row.className = `dashboard-account-row${isCurrent ? " is-current" : ""}`;
    row.dataset.dashboardAccount = account.id;

    const name = document.createElement("span");
    name.className = "dashboard-account-name";
    name.textContent = account.account_name;
    const port = document.createElement("small");
    port.textContent = `端口 ${account.chrome_debug_port}`;
    name.append(port);
    row.append(name);

    const savedSongs = lyricItem?.result?.saved?.length
      ? lyricItem.result.saved
      : accountSongs;
    if (savedSongs.length) {
      row.title = savedSongs.map((song) => song.song_name).join("、");
    }

    for (const value of [
      accountSongsLoaded || lyricItem || isCurrent ? accountLyricCount : "-",
      isCurrent ? successful : "-",
      isCurrent && state.uploads ? dailyUsed : "-",
      lyricItem ? (lyricItem.status === "failed" ? 1 : 0) : isCurrent ? failed : "-",
    ]) {
      const cell = document.createElement("span");
      cell.textContent = String(value);
      row.append(cell);
    }

    const status = document.createElement("span");
    status.className = "dashboard-account-status";
    if (queueItem) {
      status.textContent = statusLabels[queueItem.status] || queueItem.status;
      status.dataset.tone = queueItem.status;
    } else if (accountLyricCount > 0) {
      status.textContent = "已生成";
      status.dataset.tone = "completed";
    } else {
      status.textContent = isCurrent ? "当前" : state.selectedTaskAccounts.has(account.id) ? "已选择" : "待选择";
      status.dataset.tone = isCurrent ? "current" : state.selectedTaskAccounts.has(account.id) ? "selected" : "idle";
    }
    row.append(status);
    table.append(row);
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

function successfulSongStatus(value) {
  return value === "success" || value === "skipped" || value === "成功" || value === "已跳过";
}

function liveGenerationRun(accountId) {
  const run = state.generationRuns[accountId];
  return run && runningStatuses().has(run.status) ? run : null;
}

function rememberGenerationRun(run) {
  if (!run?.account_id) return;
  state.generationRuns[run.account_id] = run;
  if (runningStatuses().has(run.status)) {
    state.dashboardSongs[run.account_id] = run.songs || [];
  }
}

function runMatchesCurrentAccount(run) {
  return Boolean(run?.account_id) && (!state.accountId || run.account_id === state.accountId);
}

function accountStateIsStale(reloadId, accountId) {
  return reloadId !== state.accountReloadId || state.accountId !== accountId;
}

function isRunning() {
  return Boolean(state.current && runningStatuses().has(state.current.status));
}

function renderTaskStatus() {
  const chip = elements["task-status"];
  if (multiStageRunning()) {
    chip.textContent = state.multiQueue.status === "stopping" ? "多账号任务停止中" : "多账号任务运行中";
    chip.className = "status-chip is-active";
    return;
  }
  if (!state.current) {
    if (uploadRunning()) {
      const waitingCode = ["waiting_verification_code", "waiting_external_verification_code"]
        .includes(state.uploadRun?.step);
      chip.textContent = waitingCode ? "等待验证码" : "上传任务运行中";
      chip.className = "status-chip is-active";
      return;
    }
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
    verification_failed: "歌词校验失败",
  };
  chip.textContent = labels[state.current.status] || state.current.status;
  chip.className = `status-chip ${runningStatuses().has(state.current.status) ? "is-active" : state.current.status === "completed" ? "is-live" : "is-warn"}`;
}

function renderAccounts() {
  const select = elements["account-select"];
  select.innerHTML = "";
  for (const account of state.accounts) {
    select.append(new Option(`${account.account_name} · ${account.chrome_debug_port}`, account.id));
  }
  select.value = state.accountId || "";
  const available = new Set(state.accounts.map((account) => account.id));
  state.selectedTaskAccounts = new Set(
    [...state.selectedTaskAccounts].filter((accountId) => available.has(accountId)),
  );
  state.monitoringSelectedAccountIds = new Set(
    [...state.monitoringSelectedAccountIds].filter((accountId) => available.has(accountId)),
  );
  if (!state.monitoringSelectedAccountIds.size && state.accountId && available.has(state.accountId)) {
    state.monitoringSelectedAccountIds.add(state.accountId);
  }
  if (state.monitoringViewAccountId !== "all" && !available.has(state.monitoringViewAccountId)) {
    state.monitoringViewAccountId = "all";
  }
  renderAccountCards();
  renderAccountEditor();
  renderTaskAccounts();
}

function todayValue() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

// The generation stage and the full pipeline share one remembered choice so a
// model picked in either place is used everywhere on this machine.
function generationModelSelects() {
  return [elements["generation-model"], elements["pipeline-model"]].filter(Boolean);
}

function generationSingerSelects() {
  return [elements["generation-singer"], elements["pipeline-singer"]].filter(Boolean);
}

function applyGenerationModel(value) {
  for (const select of generationModelSelects()) {
    if ([...select.options].some((option) => option.value === value)) select.value = value;
  }
  state.generationModel = value;
}

function applyGenerationSinger(value) {
  for (const select of generationSingerSelects()) {
    if ([...select.options].some((option) => option.value === value)) select.value = value;
  }
  state.generationSinger = value;
}

function multiStageRunning() {
  return Boolean(state.multiQueue && ["running", "stopping"].includes(state.multiQueue.status));
}

async function saveUploadContractMode(accountId, mode) {
  if (!UPLOAD_CONTRACT_MODE_LABELS[mode]) return;
  const index = state.accounts.findIndex((item) => item.id === accountId);
  if (index < 0) return;
  const account = state.accounts[index];
  if (account.upload_contract_mode === mode) return;

  const previousAccount = account;
  state.uploadContractSavingIds.add(accountId);
  state.accounts[index] = { ...account, upload_contract_mode: mode };
  renderTaskAccounts();

  try {
    const updated = await api(`/api/accounts/${accountId}`, {
      method: "PUT",
      body: JSON.stringify({
        ...state.accounts[index],
        upload_contract_mode: mode,
      }),
    });
    state.accounts = state.accounts.map((item) => item.id === updated.id ? updated : item);
    if (state.editingAccountId === updated.id) fillAccountForm(updated);
    const uploadState = state.stageUploads[updated.id];
    if (uploadState) {
      state.stageUploads[updated.id] = {
        ...uploadState,
        contract_mode: updated.upload_contract_mode,
        contract_mode_name: UPLOAD_CONTRACT_MODE_LABELS[updated.upload_contract_mode],
      };
    }
    toast(`${updated.account_name} 签约模式已保存：${UPLOAD_CONTRACT_MODE_LABELS[mode]}`);
  } catch (error) {
    state.accounts[state.accounts.findIndex((item) => item.id === accountId)] = previousAccount;
    toast(error.message, true);
  } finally {
    state.uploadContractSavingIds.delete(accountId);
    renderTaskAccounts();
  }
}

function renderTaskAccounts() {
  const stageMeta = {
    lyrics: { title: "AI 作词", caption: "全部账号 · 并联执行" },
    generation: { title: "生成下载", caption: "全部账号 · 最多 2 个并联执行" },
    upload: { title: "上传发布", caption: "全部账号 · 最多 2 个并联执行" },
    pipeline: { title: "完整流水线", caption: "全部账号 · 按队列串联" },
  }[state.stage] || { title: "任务", caption: "全部账号" };
  elements["workflow-title"].textContent = stageMeta.title;
  elements["workflow-caption"].textContent = stageMeta.caption;
  const selectedAccounts = selectedTaskAccounts();
  const selectedAccountText = selectedAccounts.map((account) => account.account_name).join("、");
  elements["task-account-count"].textContent = selectedAccountText
    ? `已选 ${selectedAccounts.length} / ${state.accounts.length}：${selectedAccountText}`
    : `已选 0 / ${state.accounts.length}`;
  elements["task-account-count"].title = selectedAccountText;
  const busy = multiStageRunning() || isRunning() || uploadRunning() || pipelineWorkflowBusy();
  elements["task-account-all"].disabled = busy || !state.accounts.length;
  elements["task-account-clear"].disabled = busy || !state.selectedTaskAccounts.size;

  const table = elements["stage-account-table"];
  table.innerHTML = "";
  table.classList.toggle("stage-account-grid", state.stage === "lyrics");
  if (state.stage === "lyrics") {
    renderLyricAccountCards(table, busy);
    renderLyricSongSummary();
    renderMultiStage();
    return;
  }

  const columns = {
    lyrics: ["选择", "账号", "状态", "歌词", "模板 / 提示词", "位置", "操作"],
    generation: ["选择", "账号", "状态", "进度", "模型 / 人声", "当前步骤", "操作"],
    upload: ["选择", "账号", "状态", "额度", "签约模式", "当前步骤", "操作"],
    pipeline: ["选择", "账号", "状态", "总进度", "队列配置", "当前阶段", "操作"],
  }[state.stage] || ["选择", "账号", "状态", "进度", "配置", "步骤", "操作"];
  const head = document.createElement("div");
  head.className = "stage-account-row stage-account-head";
  for (const column of columns) {
    const cell = document.createElement("span");
    cell.textContent = column;
    head.append(cell);
  }
  table.append(head);

  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "stage-account-row stage-account-empty";
    empty.textContent = "账号管理中暂无账号";
    table.append(empty);
    renderMultiStage();
    return;
  }

  state.accounts.forEach((account) => {
    const row = document.createElement("div");
    row.className = `stage-account-row${state.selectedTaskAccounts.has(account.id) ? " is-selected" : ""}${
      state.stage === "generation" && account.id === state.accountId ? " is-viewing" : ""
    }`;
    row.dataset.stageAccount = account.id;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedTaskAccounts.has(account.id);
    checkbox.disabled = busy;
    checkbox.dataset.taskAccount = account.id;

    const selectCell = document.createElement("span");
    selectCell.className = "stage-account-select";
    selectCell.append(checkbox);

    const accountCell = document.createElement("span");
    accountCell.className = "stage-account-name";
    accountCell.innerHTML = "<strong></strong><small></small>";
    accountCell.querySelector("strong").textContent = account.account_name;
    accountCell.querySelector("small").textContent = `端口 ${account.chrome_debug_port}`;

    const run = liveGenerationRun(account.id);
    const songs = run?.songs?.length ? run.songs : state.dashboardSongs[account.id] || [];
    const successCount = songs.filter((song) => successfulSongStatus(song.status)).length;
    const failureCount = songs.filter((song) => isFailureStatus(song.status)).length;
    const upload = state.stageUploads[account.id];
    const uploadRun = state.uploadRuns[account.id];
    const templates = state.accountTemplates[account.id] || [];
    const template = templates.find((item) => item.id === state.selectedLyricTemplateId && item.account_id === account.id) || templates[0];
    const queueActive = Boolean(state.multiQueue && state.multiQueue.day === todayValue() && (
      state.multiQueue.stage === state.stage
      || (state.stage === "generation" && state.multiQueue.stage === "repair")
    ));
    const queueItem = queueActive
      ? state.multiQueue?.items.find((item) => item.account_id === account.id)
      : null;

    const statusLabels = { pending: "等待", running: "处理中", completed: "成功", failed: "失败", stopped: "停止" };
    let statusText = "等待";
    let statusTone = "waiting";
    if (queueItem) {
      statusText = statusLabels[queueItem.status] || queueItem.status;
      statusTone = queueItem.status === "completed" ? "completed" : queueItem.status === "running" ? "running" : queueItem.status;
    } else if (queueActive) {
      statusText = "未入队";
      statusTone = "idle";
    } else if (state.stage === "lyrics" && songs.length) {
      statusText = "已生成";
      statusTone = "completed";
    } else if (state.stage === "generation" && failureCount) {
      statusText = "有异常";
      statusTone = "failed";
    } else if (state.stage === "generation" && successCount) {
      statusText = "已下载";
      statusTone = "completed";
    } else if (state.stage === "upload" && upload && Number(upload.daily_used || 0) > 0) {
      statusText = "已发布";
      statusTone = "completed";
    } else if (state.stage === "pipeline" && state.pipelineQueue) {
      const pipelineItem = state.pipelineQueue.items.find((item) => item.account_id === account.id);
      if (pipelineItem) {
        statusText = statusLabels[pipelineItem.status] || pipelineItem.status;
        statusTone = pipelineItem.status;
      }
    }

    const statusCell = document.createElement("span");
    const statusPill = document.createElement("span");
    statusPill.className = `state state-${statusTone}`;
    statusPill.textContent = statusText;
    statusCell.append(statusPill);

    const progress = {
      lyrics: `${songs.length} 首`,
      generation: `${successCount} / ${songs.length}`,
      upload: upload ? `${upload.daily_used || 0} / ${upload.daily_limit || 10}` : "-",
      pipeline: `${successCount} / ${songs.length}`,
    }[state.stage] || "-";
    const progressCell = document.createElement("span");
    progressCell.textContent = progress;

    let configText = "-";
    let configSub = "";
    let stepText = "-";
    if (state.stage === "lyrics") {
      configText = template?.name || "未设置模板";
      configSub = template ? `生成 ${template.generation_count} 首` : "点击修改创建";
      stepText = joinDayFolder(account.lyric_dir, todayValue());
    } else if (state.stage === "generation") {
      configText = account.model_name || "自动";
      configSub = account.model_name === SWAY_MODEL_NAME
        ? (account.singer_name ? `人声：${account.singer_name}` : "人声：平台默认")
        : "人声：不适用";
      const runningSong = songs.find((song) => song.status === "running");
      const failedSong = songs.find((song) => isFailureStatus(song.status));
      stepText = run
        ? stepLabel(run.current_step)
        : queueItem?.status === "running" && runningSong
        ? stepLabel(runningSong.current_step)
        : failedSong ? stateLabel(failedSong.status) : successCount === songs.length && songs.length ? "完成" : "等待";
    } else if (state.stage === "upload") {
      configSub = `艺人：${account.upload_artist_name || "-"} · AI 创作${
        state.uploadAiCreated ? "是" : "否"
      } · 上限 ${account.upload_batch_size}`;
      stepText = uploadRun
        ? (runningStatuses().has(uploadRun.status) ? stepLabel(uploadRun.step) : stateLabel(uploadRun.status))
        : upload ? `待发布 ${upload.files?.length || 0} 首` : "-";
    } else if (state.stage === "pipeline") {
      configText = template?.name || "未设置模板";
      configSub = `AI 创作${elements["pipeline-ai-created"].value === "yes" ? "是" : "否"}`;
      stepText = state.pipelineQueue?.items?.find((item) => item.account_id === account.id)?.stage || "等待";
    }

    const configCell = document.createElement("span");
    configCell.className = "stage-account-config";
    if (state.stage === "upload") {
      const contractField = document.createElement("label");
      contractField.className = "upload-contract-field";
      contractField.dataset.tip = "保存到账号配置；后续上传发布默认使用该模式。";

      const contractTitle = document.createElement("span");
      contractTitle.textContent = "签约模式";

      const contractSelect = document.createElement("select");
      contractSelect.disabled = busy || state.uploadContractSavingIds.has(account.id);
      contractSelect.dataset.contractAccount = account.id;
      contractSelect.setAttribute("aria-label", `${account.account_name} 签约模式`);
      for (const mode of UPLOAD_CONTRACT_MODES) {
        contractSelect.append(new Option(mode.label, mode.value));
      }
      contractSelect.value = account.upload_contract_mode || "exclusive_authorization";

      contractField.append(contractTitle, contractSelect);
      configCell.append(contractField);

      const configMeta = document.createElement("small");
      configMeta.className = "stage-account-config-meta";
      configMeta.textContent = configSub;
      configCell.append(configMeta);
    } else {
      configCell.innerHTML = "<strong></strong>";
      configCell.querySelector("strong").textContent = configText;
      const configMeta = document.createElement("small");
      configMeta.textContent = configSub;
      configCell.append(configMeta);
    }
    configCell.title = configSub;

    const stepCell = document.createElement("span");
    stepCell.className = "stage-account-step";
    stepCell.textContent = stepText;
    stepCell.title = stepText;

    const actionCell = document.createElement("span");
    actionCell.className = "stage-account-actions";
    if (state.stage === "generation") {
      const view = document.createElement("button");
      view.type = "button";
      view.className = "button stage-account-action";
      view.textContent = "查看";
      view.dataset.focusAccount = account.id;
      view.disabled = account.id === state.accountId;
      actionCell.append(view);
    }
    const action = document.createElement("button");
    action.type = "button";
    action.className = "button stage-account-action";
    if (state.stage === "lyrics" || state.stage === "generation") {
      action.textContent = "修改";
      action.dataset.editStageAccount = account.id;
      action.disabled = busy;
    } else {
      action.textContent = "查看";
      action.dataset.focusAccount = account.id;
      action.disabled = account.id === state.accountId;
    }
    actionCell.append(action);

    row.append(selectCell, accountCell, statusCell, progressCell, configCell, stepCell, actionCell);
    table.append(row);
  });
  renderMultiStage();
}

function renderLyricAccountCards(container, busy) {
  container.innerHTML = "";
  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "lyric-account-empty";
    empty.textContent = "账号管理中暂无账号";
    container.append(empty);
    return;
  }

  const statusLabels = {
    pending: "排队中",
    running: "正在生成",
    completed: "已完成",
    failed: "生成失败",
    stopped: "已停止",
  };
  const queue = state.multiQueue?.stage === "lyrics" && state.multiQueue.day === todayValue()
    ? state.multiQueue
    : null;

  state.accounts.forEach((account) => {
    const card = document.createElement("article");
    card.className = `lyric-account-card${state.selectedTaskAccounts.has(account.id) ? " is-selected" : ""}`;
    card.dataset.stageAccount = account.id;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedTaskAccounts.has(account.id);
    checkbox.disabled = busy;
    checkbox.dataset.taskAccount = account.id;
    checkbox.setAttribute("aria-label", `选择 ${account.account_name}`);

    const identity = document.createElement("div");
    identity.className = "lyric-account-identity";
    const name = document.createElement("strong");
    name.textContent = account.account_name;
    name.title = account.account_name;
    const port = document.createElement("small");
    port.textContent = `端口 ${account.chrome_debug_port}`;
    identity.append(name, port);

    const selectCell = document.createElement("label");
    selectCell.className = "lyric-account-select";
    selectCell.append(checkbox);

    const header = document.createElement("div");
    header.className = "lyric-account-header";
    header.append(selectCell, identity);

    const queueItem = queue?.items.find((item) => item.account_id === account.id) || null;
    const songs = state.dashboardSongs[account.id] || [];
    const templates = state.accountTemplates[account.id] || [];
    const template = templates.find((item) => item.id === state.selectedLyricTemplateId) || templates[0];
    const resultCount = Number(queueItem?.result?.saved_count ?? queueItem?.result?.generated_count ?? 0);
    const generatedCount = resultCount || songs.length;
    let statusText = songs.length ? "已生成" : template ? "待执行" : "未配置";
    let statusTone = songs.length ? "completed" : "waiting";
    if (queueItem) {
      statusText = statusLabels[queueItem.status] || queueItem.status;
      statusTone = queueItem.status === "completed" ? "completed" : queueItem.status;
    }

    const status = document.createElement("span");
    status.className = `state state-${statusTone}`;
    status.textContent = statusText;

    const titleRow = document.createElement("div");
    titleRow.className = "lyric-account-title-row";
    titleRow.append(header, status);

    const metrics = document.createElement("dl");
    metrics.className = "lyric-account-metrics";
    const metricItems = [
      ["目标", template ? `${template.generation_count} 首` : "-"],
      [queueItem?.status === "running" ? "目录已有" : "已生成", `${generatedCount} 首`],
      ["模板", template?.name || "未设置"],
    ];
    metricItems.forEach(([label, value]) => {
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value;
      detail.title = value;
      metrics.append(term, detail);
    });

    const actionRow = document.createElement("div");
    actionRow.className = "lyric-account-actions";
    const action = document.createElement("button");
    action.type = "button";
    action.className = "button lyric-account-edit";
    action.textContent = "修改";
    action.dataset.editStageAccount = account.id;
    action.disabled = busy;
    actionRow.append(action);

    card.append(titleRow, metrics, actionRow);
    container.append(card);
  });
}

function renderLyricSongSummary() {
  const container = elements["lyric-summary-list"];
  container.innerHTML = "";
  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state lyric-summary-empty";
    empty.textContent = "暂无账号";
    container.append(empty);
    elements["lyric-summary-caption"].textContent = "按账号显示今日生成状态和歌名";
    return;
  }

  const statusLabels = {
    pending: "排队中",
    running: "正在生成",
    completed: "已完成",
    failed: "生成失败",
    stopped: "已停止",
  };
  const queue = state.multiQueue?.stage === "lyrics" && state.multiQueue.day === todayValue()
    ? state.multiQueue
    : null;
  let generatedTotal = 0;

  state.accounts.forEach((account) => {
    const queueItem = queue?.items.find((item) => item.account_id === account.id) || null;
    const songs = queueItem?.result?.saved?.length
      ? queueItem.result.saved
      : state.dashboardSongs[account.id] || [];
    generatedTotal += songs.length;

    const card = document.createElement("article");
    card.className = "lyric-summary-card";
    card.dataset.lyricSummaryAccount = account.id;
    const main = document.createElement("div");
    main.className = "lyric-summary-main";
    const identity = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = account.account_name;
    name.title = account.account_name;
    const count = document.createElement("small");
    count.textContent = `${songs.length} 首`;
    identity.append(name, count);

    let statusText = songs.length ? "已生成" : "待生成";
    let statusTone = songs.length ? "completed" : "waiting";
    if (queueItem) {
      statusText = statusLabels[queueItem.status] || queueItem.status;
      statusTone = queueItem.status === "completed" ? "completed" : queueItem.status;
    }
    const status = document.createElement("span");
    status.className = `state state-${statusTone}`;
    status.textContent = statusText;
    main.append(identity, status);

    const list = document.createElement("ul");
    list.className = "lyric-summary-songs";
    if (!songs.length) {
      const item = document.createElement("li");
      item.className = "lyric-summary-song-empty";
      item.textContent = queueItem?.status === "running" ? "生成完成后显示歌名" : "暂无歌词";
      list.append(item);
    } else {
      songs.forEach((song) => {
        const item = document.createElement("li");
        const songName = document.createElement("strong");
        songName.textContent = song.song_name || song.file_name || "未命名歌曲";
        songName.title = songName.textContent;
        const detail = document.createElement("small");
        detail.textContent = song.valid === false ? "歌词解析失败" : song.file_name || "歌词已保存";
        detail.title = song.path || detail.textContent;
        item.append(songName, detail);
        list.append(item);
      });
    }

    card.append(main, list);
    container.append(card);
  });

  elements["lyric-summary-caption"].textContent = `今日 ${todayValue()} · 共 ${generatedTotal} 首`;
}

function renderMultiStage() {
  const queue = state.multiQueue;
  const caption = elements["multi-stage-caption"];
  if (!queue) {
    caption.textContent = "未启动多账号任务";
    caption.className = "task-account-summary";
    renderDashboard();
    return;
  }
  const completed = queue.items.filter((item) => item.status === "completed").length;
  const failed = queue.items.filter((item) => item.status === "failed").length;
  const current = queue.items[queue.current_index];
  const stageLabels = { lyrics: "AI 作词", generation: "生成下载", repair: "一键修复", upload: "上传发布" };
  caption.textContent = `${stageLabels[queue.stage] || queue.stage}：成功 ${completed}，失败 ${failed} / ${queue.items.length}${
    queue.status === "running" && current ? `；当前 ${current.account_name}` : ""
  }${queue.status === "stopping" ? "；正在停止" : ""}`;
  caption.className = `task-account-summary${failed ? " is-failed" : queue.status === "running" ? " is-live" : ""}`;
  caption.title = queue.items
    .map((item) => `${item.account_name}: ${item.status}${item.error ? ` (${item.error})` : ""}`)
    .join("\n");
  renderDashboard();
}

function restoreGenerationModel() {
  let value = "自动";
  try {
    value = localStorage.getItem(GENERATION_MODEL_STORAGE_KEY) || "自动";
  } catch {
    value = "自动";
  }
  const select = elements["generation-model"];
  if (![...select.options].some((option) => option.value === value)) value = "自动";
  applyGenerationModel(value);
}

function saveGenerationModel(value) {
  applyGenerationModel(value);
  renderGenerationModelControls();
  try {
    localStorage.setItem(GENERATION_MODEL_STORAGE_KEY, value);
  } catch {
    // Storage can be unavailable in restricted browser profiles.
  }
}

function restoreGenerationSinger() {
  let value = "";
  try {
    value = localStorage.getItem(GENERATION_SINGER_STORAGE_KEY) ?? "";
  } catch {
    value = "";
  }
  const select = elements["generation-singer"];
  if (![...select.options].some((option) => option.value === value)) value = "";
  applyGenerationSinger(value);
}

function saveGenerationSinger(value) {
  applyGenerationSinger(value);
  try {
    localStorage.setItem(GENERATION_SINGER_STORAGE_KEY, value);
  } catch {
    // Storage can be unavailable in restricted browser profiles.
  }
}

function renderGenerationModelControls(locked) {
  const visible = elements["generation-model"].value === SWAY_MODEL_NAME;
  const disabled = Boolean(locked);
  for (const select of generationModelSelects()) select.disabled = disabled;
  for (const select of generationSingerSelects()) {
    const field = select.closest(".singer-field");
    if (field) field.hidden = !visible;
    select.disabled = disabled || !visible;
  }
}

function renderGenerationSingerVisibility() {
  const visible = elements["generation-model"].value === SWAY_MODEL_NAME;
  const field = elements["generation-singer"].closest(".singer-field");
  field.hidden = !visible;
  const select = elements["generation-singer"];
  select.disabled = !visible;
  if (!visible && select.value) {
    select.value = "";
    saveGenerationSinger("");
  }
}

function renderAccountSingerVisibility() {
  const visible = elements["account-model-select"].value === SWAY_MODEL_NAME;
  const select = elements["account-singer-select"];
  select.closest(".account-singer-field").hidden = !visible;
  select.disabled = !visible;
  if (!visible) select.value = "";
}

function singerNameForModel(modelName, singerName = "") {
  return modelName === SWAY_MODEL_NAME ? (singerName || "") : "";
}

function joinDayFolder(root, day) {
  return `${String(root || "").replace(/[\\/]+$/, "")}\\${day}`;
}

function renderAccountCards() {
  const container = elements["account-cards"];
  container.innerHTML = "";
  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state account-empty";
    const title = document.createElement("strong");
    title.textContent = "暂无账号";
    const caption = document.createElement("p");
    caption.textContent = "点击右上角“新建”添加妙响账号。";
    empty.append(title, caption);
    container.append(empty);
    return;
  }

  for (const account of state.accounts) {
    const card = document.createElement("article");
    card.className = `account-card${account.id === state.accountId ? " is-current" : ""}`;
    card.dataset.accountId = account.id;
    card.tabIndex = 0;
    card.setAttribute("aria-label", `选择账号 ${account.account_name}`);

    const main = document.createElement("div");
    main.className = "account-card-main";
    const name = document.createElement("h3");
    name.textContent = account.account_name;
    name.title = account.account_name;
    main.append(name);
    if (account.id === state.accountId) {
      const badge = document.createElement("span");
      badge.className = "account-current-badge";
      badge.textContent = "当前";
      main.append(badge);
    }
    if (state.loginBrowser?.account_id === account.id) {
      const browserBadge = document.createElement("span");
      browserBadge.className = "account-browser-badge";
      browserBadge.textContent = "登录窗口已打开";
      main.append(browserBadge);
    }

    const actions = document.createElement("div");
    actions.className = "account-card-actions";

    if (state.loginBrowser?.account_id === account.id) {
      const closeBrowser = document.createElement("button");
      closeBrowser.type = "button";
      closeBrowser.className = "button";
      closeBrowser.textContent = "关闭窗口";
      closeBrowser.dataset.closeBrowserAccount = account.id;
      closeBrowser.dataset.tip = "关闭该账号登录窗口，释放 Chrome 用户目录。";
      closeBrowser.disabled = isRunning() || uploadRunning();
      actions.append(closeBrowser);
    } else {
      const login = document.createElement("button");
      login.type = "button";
      login.className = "button primary";
      login.textContent = "登录账号";
      login.dataset.loginAccount = account.id;
      login.dataset.tip = "打开该账号专用 Chrome；如已有其它登录窗口，会先关闭。登录后看到账号头像，再等 10 秒关闭。";
      login.disabled = isRunning() || uploadRunning();
      actions.append(login);
    }

    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "button";
    edit.textContent = "修改";
    edit.dataset.editAccount = account.id;
    edit.disabled = isRunning();

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button danger";
    remove.textContent = "删除账号";
    remove.dataset.deleteAccount = account.id;
    remove.dataset.tip = "删除控制台账号配置，并删除它绑定的 Chrome 用户目录；不会删除歌词和音乐文件。";
    remove.disabled = isRunning() || uploadRunning();

    actions.append(edit, remove);

    card.append(main, actions);
    container.append(card);
  }
}

function renderAccountEditor() {
  elements["account-cards"].hidden = state.accountEditorOpen;
  elements["account-form"].hidden = !state.accountEditorOpen;
  elements["account-cancel"].hidden = !state.accountEditorOpen;
}

function aiApiConfigs() {
  return state.settings?.ai_api_configs || [];
}

function activeAiApiConfig() {
  const configs = aiApiConfigs();
  return configs.find((item) => item.id === state.settings?.active_ai_api_config_id) || configs[0] || null;
}

function fillAiApiForm(config = null) {
  const form = elements["ai-settings-form"];
  form.ai_provider_id.value = config?.id || "";
  form.ai_provider_name.value = config?.name || "";
  form.ai_api_base_url.value = config?.api_base_url || "";
  form.ai_api_key.value = config?.api_key || "";
  form.ai_model.value = config?.model || "";
  form.ai_max_retries.value = config?.max_retries ?? 2;
}

function syncAiProviderSelect() {
  const select = elements["ai-provider-select"];
  const configs = aiApiConfigs();
  const active = activeAiApiConfig();
  select.innerHTML = "";
  if (!configs.length) {
    select.append(new Option("请先配置 AI 接口", ""));
  } else {
    for (const config of configs) {
      select.append(new Option(`${config.name} · ${config.model}`, config.id));
    }
  }
  select.value = active?.id || "";
  select.disabled = !configs.length || isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
}

function renderSettingsTabs() {
  const runtimeActive = state.settingsTab === "runtime";
  const aiActive = state.settingsTab === "ai";
  const promptActive = state.settingsTab === "prompt";
  const aiConfigured = Boolean(activeAiApiConfig());
  const showAiForm = aiActive && (!aiConfigured || state.aiConfigEditorOpen);
  const showAiCard = aiActive && aiConfigured && !state.aiConfigEditorOpen;
  const templatePanel = document.querySelector(".lyric-template-panel");
  if (templatePanel) templatePanel.hidden = !promptActive;
  elements["settings-subnav"].hidden = state.view !== "settings";
  elements["settings-tab-runtime"].classList.toggle("is-active", runtimeActive);
  elements["settings-tab-ai"].classList.toggle("is-active", aiActive);
  elements["settings-tab-prompt"].classList.toggle("is-active", promptActive);
  elements["settings-form"].hidden = !runtimeActive;
  elements["ai-config-cards"].hidden = !showAiCard;
  elements["ai-settings-form"].hidden = !showAiForm;
  elements["lyric-prompt-panel"].hidden = !promptActive;
  elements["ai-config-cancel"].hidden = !state.aiConfigEditorOpen;
  elements["save-settings"].hidden = promptActive || (aiActive && !showAiForm);
  elements["save-settings"].textContent = runtimeActive ? "保存参数" : "保存并使用";
  if (showAiCard) renderAiApiConfigCards();
  syncAiProviderSelect();
}

function maskApiKey(key) {
  if (!key) return "未填写";
  if (key.length <= 8) return "****";
  return `${key.slice(0, 4)}****${key.slice(-4)}`;
}

function renderAiApiConfigCards() {
  const container = elements["ai-config-cards"];
  const configs = aiApiConfigs();
  container.innerHTML = "";

  const toolbar = document.createElement("div");
  toolbar.className = "ai-config-toolbar";
  const caption = document.createElement("span");
  caption.textContent = `已配置 ${configs.length} 个 AI 接口`;
  const add = document.createElement("button");
  add.type = "button";
  add.className = "button";
  add.textContent = "新增接口";
  add.dataset.addAiConfig = "true";
  add.disabled = isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  toolbar.append(caption, add);
  container.append(toolbar);

  if (!configs.length) return;

  for (const config of configs) {
    const active = config.id === state.settings?.active_ai_api_config_id;
    const check = state.aiApiChecks[config.id];
    const anyChecking = Object.values(state.aiApiChecks).some((item) => item.status === "checking");

  const card = document.createElement("article");
  card.className = "settings-card is-ai";
  const main = document.createElement("div");
  main.className = "settings-card-main";
  const title = document.createElement("h3");
  title.textContent = config.name;
  title.title = config.name;
  const badge = document.createElement("span");
  badge.className = `state ${active ? "state-success" : "state-pending"}`;
  badge.textContent = active ? "使用中" : "备用";
  main.append(title, badge);

  const details = document.createElement("dl");
  details.className = "settings-card-details";
  let checkText = "未检测";
  if (check?.status === "checking") checkText = "检测中...";
  else if (check?.status === "success") checkText = `可用 · 模型 ${check.model_count} 个 · ${check.elapsed_ms} ms`;
  else if (check?.status === "failed") checkText = `失败 · ${check.error || "未知错误"}`;
  for (const [label, value] of [
    ["API Base URL", config.api_base_url],
    ["模型", config.model],
    ["API Key", maskApiKey(config.api_key)],
    ["重试次数", String(config.max_retries)],
    ["检测", checkText],
  ]) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    description.title = value;
    if (label === "检测") {
      description.className = `ai-check-result is-${check?.status || "idle"}`;
      description.title = checkText;
    }
    details.append(term, description);
  }

  const actions = document.createElement("div");
  actions.className = "settings-card-actions";
  const use = document.createElement("button");
  use.type = "button";
  use.className = "button";
  use.textContent = active ? "正在使用" : "使用";
  use.dataset.useAiConfig = config.id;
  use.disabled = active || isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "button";
  edit.textContent = "修改";
  edit.dataset.editAiConfig = config.id;
  edit.disabled = isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  const test = document.createElement("button");
  test.type = "button";
  test.className = "button";
  test.textContent = check?.status === "checking" ? "检测中" : "检测";
  test.dataset.testAiConfig = config.id;
  test.disabled = anyChecking || isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "button danger";
  remove.textContent = "删除";
  remove.dataset.deleteAiConfig = config.id;
  remove.disabled = isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  actions.append(use, test, edit, remove);

  card.append(main, details, actions);
  container.append(card);
  }
}

function renderLyricWorkspace() {
  if (document.activeElement !== elements["lyric-system-prompt"]) {
    elements["lyric-system-prompt"].value = state.lyricSystemPrompt || "";
  }
  renderLyricPromptState();
  renderTemplateAccountOptions();
  renderTemplateOutputLocation();
  renderLyricTemplateCards();
  renderLyricTemplateEditor();
  renderLyricProgress();
  renderLyricResults();
  renderLyricControls();
  renderPipelinePanel();
}

function renderLyricProgress() {
  const progress = state.lyricProgress;
  elements["lyric-progress-panel"].hidden = !progress;
  if (!progress) return;

  const elapsed = state.lyricGenerating && state.lyricProgressStartedAt
    ? Math.max(0, Math.round((Date.now() - state.lyricProgressStartedAt) / 1000))
    : Math.round(progress.elapsed_seconds || 0);
  const expected = progress.expected_count || 0;
  const names = progress.song_names || [];
  const stageLabels = {
    connecting: "连接 AI API",
    thinking: "AI 正在整理创作思路",
    generating: "AI 正在输出歌词",
    parsing: "校验返回结果",
    repairing: "仅重写未通过歌曲",
    retrying: "准备重试",
    failed: "生成失败",
    completed: "生成完成",
  };

  elements["lyric-progress-message"].textContent = progress.message || stageLabels[progress.stage] || "生成中";
  elements["lyric-progress-elapsed"].textContent = `${elapsed} 秒`;
  elements["lyric-progress-chars"].textContent = `${progress.content_chars || 0} 字符`;
  elements["lyric-progress-count"].textContent = `${names.length} / ${expected}`;
  elements["lyric-progress-names"].textContent = names.join("、");
  elements["lyric-progress-reasoning"].textContent = progress.reasoning_available
    ? `模型动态：${progress.reasoning_excerpt || "已收到思考内容"}`
    : progress.stage === "thinking"
      ? "该接口未返回思考内容，但请求仍在保持连接"
      : "";
}

function parseSSEBlock(block) {
  const lines = block.split(/\r?\n/);
  const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
  const data = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");
  return { event, data };
}

async function generateLyricsStream(accountId, templateId) {
  const response = await fetch(`/api/accounts/${accountId}/lyrics/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_id: templateId }),
  });
  if (!response.ok) {
    let message = `请求失败 ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(message);
  }
  if (!response.body) throw new Error("当前浏览器不支持流式进度");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const consumeBlock = (block) => {
    if (!block.trim()) return null;
    const message = parseSSEBlock(block);
    if (!message.data) return null;
    const payload = JSON.parse(message.data);
    if (message.event === "progress") {
      state.lyricProgress = payload;
      renderLyricProgress();
      return null;
    }
    return { event: message.event, payload };
  };

  while (true) {
    const { value, done } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    if (done) buffer += decoder.decode();

    let separator = buffer.search(/\r?\n\r?\n/);
    while (separator >= 0) {
      const block = buffer.slice(0, separator);
      const match = buffer.slice(separator).match(/^\r?\n\r?\n/);
      buffer = buffer.slice(separator + (match?.[0].length || 2));
      const result = consumeBlock(block);
      if (result?.event === "done") return result.payload;
      if (result?.event === "error") throw new Error(result.payload.message || "AI 作词失败");
      separator = buffer.search(/\r?\n\r?\n/);
    }
    if (done) break;
  }
  throw new Error("AI 连接中断，未收到完整结果");
}

function renderLyricControls() {
  const disabled = !state.accountId || !state.selectedLyricTemplateId || state.lyricGenerating || isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  document.querySelectorAll("[data-generate-template]").forEach((button) => {
    button.disabled = disabled || button.dataset.generateTemplate !== state.selectedLyricTemplateId;
    button.textContent = state.lyricGenerating ? "生成中" : "生成歌词";
  });
  elements["save-lyrics"].disabled = !state.accountId || !state.lyricResults.length || state.lyricGenerating || isRunning() || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  elements["multi-lyrics-start"].disabled = !state.selectedTaskAccounts.size || !activeAiApiConfig() || state.lyricGenerating || multiStageRunning() || isRunning() || uploadRunning() || pipelineWorkflowBusy();
  elements["multi-lyrics-start"].textContent = state.multiQueue?.stage === "lyrics" && multiStageRunning() ? "作词中" : "开始作词";
  elements["multi-lyrics-start"].dataset.tip = activeAiApiConfig()
    ? `使用 ${activeAiApiConfig().name} 为勾选账号并联生成歌词`
    : "请先在系统设置中配置 AI 接口";
}

function renderLyricPromptState() {
  const busy = state.lyricPromptSaving || isRunning() || uploadRunning();
  const hasSavedPrompt = Boolean(state.lyricSystemPrompt);
  elements["lyric-system-prompt"].disabled = busy;
  elements["save-lyric-prompt"].disabled = busy || (!state.lyricPromptDirty && hasSavedPrompt);
  elements["save-lyric-prompt"].textContent = state.lyricPromptSaving
    ? "保存中"
    : state.lyricPromptDirty
      ? "保存修改"
      : hasSavedPrompt
        ? "已保存"
        : "保存通用规则";
  elements["save-lyric-prompt"].classList.toggle("is-dirty", state.lyricPromptDirty);
  elements["lyric-prompt-details"].open = state.lyricPromptDirty || state.lyricPromptSaving;
}

function renderTemplateAccountOptions() {
  const select = elements["template-account-select"];
  const previous = select.value || state.accountId;
  select.innerHTML = "";
  for (const account of state.accounts) {
    select.append(new Option(account.account_name, account.id));
  }
  select.value = state.accounts.some((account) => account.id === previous) ? previous : state.accountId || "";
}

function renderTemplateOutputLocation() {
  const accountId = elements["template-account-select"].value || state.accountId;
  const account = state.accounts.find((item) => item.id === accountId);
  elements["template-output-location"].value = account
    ? joinDayFolder(account.lyric_dir, todayValue())
    : "";
}

function renderLyricTemplateCards() {
  const container = elements["lyric-template-cards"];
  container.innerHTML = "";
  elements["lyric-template-caption"].textContent = state.accountId
    ? `${state.accounts.find((item) => item.id === state.accountId)?.account_name || ""} · ${state.lyricTemplates.length} 个模板`
    : "选择账号后管理模板";

  if (!state.lyricTemplates.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state lyric-template-empty";
    const title = document.createElement("strong");
    title.textContent = "暂无模板";
    const caption = document.createElement("p");
    caption.textContent = "点击“新建模板”创建账号专属模板。";
    empty.append(title, caption);
    container.append(empty);
    return;
  }

  for (const template of state.lyricTemplates) {
    const account = state.accounts.find((item) => item.id === template.account_id);
    const card = document.createElement("article");
    card.className = `lyric-template-card${template.id === state.selectedLyricTemplateId ? " is-selected" : ""}`;
    const main = document.createElement("div");
    main.className = "lyric-template-main";
    const name = document.createElement("strong");
    name.textContent = template.name;
    const bound = document.createElement("span");
    bound.className = "state state-running";
    bound.textContent = account?.account_name || "未知账号";
    main.append(name, bound);
    const location = document.createElement("small");
    location.className = "lyric-template-location";
    location.textContent = joinDayFolder(account?.lyric_dir || "", todayValue());
    main.append(location);

    const songStyle = document.createElement("p");
    songStyle.textContent = template.song_style;
    const lyricTone = document.createElement("p");
    lyricTone.textContent = template.lyric_tone;
    const count = document.createElement("p");
    count.textContent = `每次生成 ${template.generation_count} 首`;
    const themes = document.createElement("div");
    themes.className = "theme-list";
    for (const theme of template.themes) {
      const chip = document.createElement("span");
      chip.className = "theme-chip";
      chip.textContent = theme;
      themes.append(chip);
    }

    const actions = document.createElement("div");
    actions.className = "lyric-template-actions";
    const use = document.createElement("button");
    use.type = "button";
    use.className = template.id === state.selectedLyricTemplateId ? "button primary" : "button";
    use.textContent = template.id === state.selectedLyricTemplateId ? "使用中" : "使用";
    use.dataset.useLyricTemplate = template.id;
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "button";
    edit.textContent = "修改";
    edit.dataset.editLyricTemplate = template.id;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button danger";
    remove.textContent = "删除";
    remove.dataset.deleteLyricTemplate = template.id;
    actions.append(use, edit, remove);

    card.append(main, themes, count, songStyle, lyricTone, actions);
    container.append(card);
  }
}

function renderLyricTemplateEditor() {
  elements["lyric-template-cards"].hidden = state.lyricTemplateEditorOpen;
  elements["new-lyric-template"].hidden = state.lyricTemplateEditorOpen;
  elements["lyric-template-form"].hidden = !state.lyricTemplateEditorOpen;
  elements["cancel-lyric-template"].hidden = !state.lyricTemplateEditorOpen;
  elements["save-lyric-template"].textContent = state.editingLyricTemplateId ? "保存修改" : "保存模板";
  elements["template-account-select"].disabled = state.editingLyricTemplateId || state.lyricTemplateAccountLocked;
  renderThemeOptions();
}

function themeOptions() {
  const saved = state.lyricTemplates.flatMap((template) => template.themes);
  const selected = state.selectedTemplateThemes.filter((theme) => !THEME_OPTIONS.includes(theme));
  return [...new Set([...THEME_OPTIONS, ...saved, ...selected])];
}

function renderThemeOptions() {
  const container = elements["template-theme-options"];
  container.innerHTML = "";
  for (const theme of themeOptions()) {
    const label = document.createElement("label");
    label.className = "theme-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = theme;
    checkbox.checked = state.selectedTemplateThemes.includes(theme);
    checkbox.dataset.themeOption = theme;
    const text = document.createElement("span");
    text.textContent = theme;
    label.append(checkbox, text);
    container.append(label);
  }
}

function renderLyricResults() {
  const container = elements["lyric-results"];
  container.innerHTML = "";
  elements["lyric-empty"].classList.toggle("is-hidden", state.lyricResults.length > 0);
  elements["lyric-result-caption"].textContent = state.lyricResults.length
    ? `${state.lyricResults.length} 首草稿待确认`
    : "生成后可编辑，再保存到歌词目录";
  elements["save-lyrics"].disabled = !state.accountId || !state.lyricResults.length || state.lyricGenerating;

  state.lyricResults.forEach((song, index) => {
    const draft = document.createElement("article");
    draft.className = "lyric-draft";

    const titleField = document.createElement("label");
    titleField.className = "field";
    const titleSpan = document.createElement("span");
    titleSpan.textContent = "歌名";
    const titleInput = document.createElement("input");
    titleInput.value = song.song_name;
    titleInput.dataset.lyricIndex = index;
    titleInput.dataset.lyricField = "song_name";
    titleField.append(titleSpan, titleInput);

    const lyricsField = document.createElement("label");
    lyricsField.className = "field";
    const lyricsSpan = document.createElement("span");
    lyricsSpan.textContent = "歌词";
    const lyricsInput = document.createElement("textarea");
    lyricsInput.rows = 12;
    lyricsInput.value = song.lyrics;
    lyricsInput.dataset.lyricIndex = index;
    lyricsInput.dataset.lyricField = "lyrics";
    lyricsField.append(lyricsSpan, lyricsInput);

    const styleField = document.createElement("label");
    styleField.className = "field";
    const styleSpan = document.createElement("span");
    styleSpan.textContent = "曲风";
    const styleInput = document.createElement("textarea");
    styleInput.rows = 4;
    styleInput.value = song.style;
    styleInput.dataset.lyricIndex = index;
    styleInput.dataset.lyricField = "style";
    styleField.append(styleSpan, styleInput);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button danger";
    remove.textContent = "删除草稿";
    remove.dataset.removeLyric = index;

    draft.append(titleField, lyricsField, styleField, remove);
    container.append(draft);
  });
}

function fillAccountForm(account = null, suggestedPort = null) {
  const form = elements["account-form"];
  const values = account || {
    account_name: "",
    chrome_profile_dir: "",
    chrome_debug_port: suggestedPort || 9222,
    lyric_dir: "",
    output_dir: "",
    download_dir: "",
    max_retries: 3,
    generation_batch_size: 2,
    upload_batch_size: 10,
    upload_artist_name: "",
    upload_real_name: "",
    upload_contract_mode: "exclusive_authorization",
    song_interval_seconds: 5,
  };
  state.accountRoot = account ? inferAccountRoot(account) : "";
  form.reset();
  for (const [key, value] of Object.entries(values)) {
    if (form.elements[key]) form.elements[key].value = value;
  }
  form.elements.upload_contract_mode.value = values.upload_contract_mode || "exclusive_authorization";
  elements["account-root-input"].value = state.accountRoot;
  state.formMode = account ? "edit" : "create";
  renderAccountDirectoryMode();
}

function accountPayload() {
  const form = elements["account-form"];
  if (state.formMode === "create") updateDerivedAccountPaths();
  const payload = {
    account_name: form.account_name.value.trim(),
    chrome_profile_dir: form.chrome_profile_dir.value.trim(),
    chrome_debug_port: Number(form.chrome_debug_port.value),
    lyric_dir: form.lyric_dir.value.trim(),
    output_dir: form.output_dir.value.trim(),
    download_dir: form.download_dir.value.trim(),
    max_retries: Number(form.max_retries.value),
    generation_batch_size: Number(form.generation_batch_size.value),
    upload_batch_size: Number(form.upload_batch_size.value),
    upload_artist_name: form.upload_artist_name.value.trim(),
    upload_real_name: form.upload_real_name.value.trim(),
    upload_contract_mode: form.upload_contract_mode.value,
    song_interval_seconds: Number(form.song_interval_seconds.value),
    create_url: DEFAULT_CREATE_URL,
    assets_url: "https://music.douyin.com/studio/assets",
  };
  if (!payload.account_name) throw new Error("请填写账号名称");
  if (state.formMode === "create" && !state.accountRoot) throw new Error("请选择账号总文件夹");
  if (!payload.chrome_profile_dir || !payload.lyric_dir || !payload.output_dir || !payload.download_dir) {
    throw new Error("请完整填写账号名称和四个目录路径");
  }
  return payload;
}

function normalizeFolderPath(value) {
  return String(value || "").trim().replace(/[\\/]+/g, "\\").replace(/\\+$/, "");
}

function inferAccountRoot(account) {
  if (!account) return "";
  const categories = new Set(["歌词", "歌曲", "下载", "Chrome", "chrome"]);
  for (const rawPath of [account.lyric_dir, account.output_dir, account.download_dir, account.chrome_profile_dir]) {
    const parts = normalizeFolderPath(rawPath).split("\\").filter(Boolean);
    if (parts.length >= 3 && categories.has(parts[parts.length - 2])) {
      return parts.slice(0, -2).join("\\");
    }
  }
  return "";
}

function safeAccountFolderName(value) {
  return value.trim().replace(/[\\/:*?"<>|]+/g, "_").replace(/\s+/g, " ").trim() || "账号";
}

function accountCategoryPath(category) {
  const root = normalizeFolderPath(state.accountRoot);
  if (!root) return "";
  return `${root}\\${category}\\${safeAccountFolderName(elements["account-form"].account_name.value)}`;
}

function updateDerivedAccountPaths() {
  if (state.formMode !== "create") return;
  const form = elements["account-form"];
  const paths = {
    lyric: accountCategoryPath("歌词"),
    output: accountCategoryPath("歌曲"),
    download: accountCategoryPath("下载"),
    chrome: accountCategoryPath("Chrome"),
  };
  elements["derived-lyric-path"].textContent = paths.lyric || "-";
  elements["derived-output-path"].textContent = paths.output || "-";
  elements["derived-download-path"].textContent = paths.download || "-";
  elements["derived-chrome-path"].textContent = paths.chrome || "-";
  form.lyric_dir.value = paths.lyric;
  form.output_dir.value = paths.output;
  form.download_dir.value = paths.download;
  form.chrome_profile_dir.value = paths.chrome;
}

function renderAccountDirectoryMode() {
  const creating = state.formMode === "create";
  elements["account-root-field"].hidden = !creating;
  elements["account-derived-paths"].hidden = !creating;
  elements["chrome-profile-field"].hidden = creating;
  elements["lyric-dir-field"].hidden = creating;
  elements["output-dir-field"].hidden = creating;
  elements["download-dir-field"].hidden = creating;
  if (creating) updateDerivedAccountPaths();
}

function formatSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function pipelineRunning() {
  return Boolean(state.pipelineRun && ["running", "waiting_user"].includes(state.pipelineRun.status));
}

function pipelineQueueRunning() {
  return Boolean(state.pipelineQueue && ["running", "waiting_user"].includes(state.pipelineQueue.status));
}

function pipelineWorkflowBusy() {
  return pipelineRunning() || pipelineQueueRunning();
}

function renderPipelineQueueBuilder() {
  const container = elements["pipeline-queue-list"];
  const existingSelections = new Map();
  container.querySelectorAll(".pipeline-queue-option").forEach((row) => {
    existingSelections.set(row.dataset.accountId, row.querySelector("select")?.value || "");
  });
  container.innerHTML = "";
  if (!state.pipelineQueueOptions.length) {
    const empty = document.createElement("p");
    empty.className = "pipeline-queue-empty";
    empty.textContent = "暂无账号";
    container.append(empty);
    return;
  }

  const busy = pipelineQueueRunning();
  for (const option of state.pipelineQueueOptions) {
    const row = document.createElement("div");
    row.className = "pipeline-queue-option";
    row.dataset.accountId = option.account_id;

    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = state.selectedPipelineQueueAccounts.has(option.account_id);
    check.disabled = busy || !option.templates.length;
    check.dataset.queueAccount = option.account_id;

    const name = document.createElement("strong");
    name.textContent = option.account_name;

    const select = document.createElement("select");
    if (!option.templates.length) {
      select.append(new Option("暂无模板", ""));
    } else {
      for (const template of option.templates) {
        select.append(new Option(`${template.template_name} · ${template.generation_count}首`, template.template_id));
      }
      const previous = existingSelections.get(option.account_id);
      select.value = option.templates.some((template) => template.template_id === previous)
        ? previous
        : option.templates[0].template_id;
    }
    select.disabled = busy || !option.templates.length;

    const up = document.createElement("button");
    up.type = "button";
    up.className = "button icon-button";
    up.textContent = "↑";
    up.title = "上移";
    up.disabled = busy;
    up.dataset.queueMoveUp = option.account_id;

    const down = document.createElement("button");
    down.type = "button";
    down.className = "button icon-button";
    down.textContent = "↓";
    down.title = "下移";
    down.disabled = busy;
    down.dataset.queueMoveDown = option.account_id;

    row.append(check, name, select, up, down);
    container.append(row);
  }
}

function selectedPipelineDetailRun() {
  const queue = state.pipelineQueue;
  const items = queue?.items || [];
  if (!queue || !items.length) {
    state.selectedPipelineDetailAccountId = "";
    return state.pipelineRun;
  }

  const selected = items.find(
    (item) => item.account_id === state.selectedPipelineDetailAccountId
  );
  const current = items[queue.current_index] || items[0];
  const detailItem = state.pipelineDetailPinned && selected ? selected : current;
  state.selectedPipelineDetailAccountId = detailItem.account_id;

  if (
    state.pipelineRun?.run_id
    && state.pipelineRun.run_id === detailItem.run_id
  ) {
    return state.pipelineRun;
  }
  return detailItem.pipeline_snapshot || null;
}

function pipelineSongs(item) {
  return item?.pipeline_snapshot?.songs || [];
}

function pipelineAccountStageComplete(item, stage) {
  const songs = pipelineSongs(item);
  if (!songs.length) return false;
  if (stage === "lyrics") {
    return songs.every((song) => song.lyrics_status === "completed");
  }
  if (stage === "generation") {
    const eligible = songs.filter((song) => song.lyrics_status === "completed");
    return Boolean(eligible.length) && eligible.every((song) => song.generation_status === "completed");
  }
  const uploaded = songs.filter((song) => song.generation_status === "completed");
  return Boolean(uploaded.length) && uploaded.every((song) =>
    song.upload_status === "completed" || song.upload_removed
  );
}

function pipelineStageProgress(item, stage) {
  const songs = pipelineSongs(item);
  if (!songs.length) return "0/0";
  if (stage === "lyrics") {
    const completed = songs.filter((song) => song.lyrics_status === "completed").length;
    return `${completed}/${songs.length}`;
  }
  if (stage === "generation") {
    const eligible = songs.filter((song) => song.lyrics_status === "completed");
    const completed = eligible.filter((song) => song.generation_status === "completed").length;
    return `${completed}/${eligible.length || songs.length}`;
  }
  const eligible = songs.filter((song) => song.generation_status === "completed");
  const completed = eligible.filter((song) =>
    song.upload_status === "completed" || song.upload_removed
  ).length;
  return `${completed}/${eligible.length || songs.length}`;
}

function renderPipelinePhaseSummary() {
  const container = elements["pipeline-phase-summary"];
  const queue = state.pipelineQueue;
  const items = queue?.items || [];
  const phases = [
    { id: "lyrics", label: "AI 作词" },
    { id: "generation", label: "生成下载" },
    { id: "upload", label: "上传发布" },
    { id: "report", label: "运行报告" },
  ];
  container.innerHTML = "";
  for (const phase of phases) {
    const cell = document.createElement("div");
    cell.className = `pipeline-phase-cell${queue?.phase === phase.id ? " is-active" : ""}`;
    const title = document.createElement("span");
    title.textContent = phase.label;
    const value = document.createElement("strong");
    if (phase.id === "report") {
      value.textContent = queue?.phase === "report" ? "生成中" : "待进入";
    } else {
      const completed = items.filter((item) => pipelineAccountStageComplete(item, phase.id)).length;
      value.textContent = `账号 ${completed}/${items.length}`;
    }
    cell.append(title, value);
    container.append(cell);
  }
}

function renderPipelineQueue() {
  renderPipelineQueueBuilder();
  renderPipelinePhaseSummary();
  const queue = state.pipelineQueue;
  const statusLabels = {
    pending: "等待中",
    running: "运行中",
    waiting_user: "等待确认",
    completed: "已完成",
    failed: "失败",
    stopped: "已停止",
    partial_failed: "部分失败",
  };
  const stageLabels = {
    pending: "等待",
    lyrics: "AI 作词",
    generation: "生成 / 导出 / 下载",
    pre_upload: "上传前确认",
    upload: "上传发布",
    report: "运行报告",
  };
  const table = elements["pipeline-queue-table"];
  table.innerHTML = "";
  const head = document.createElement("div");
  head.className = "pipeline-row pipeline-head pipeline-queue-row";
  for (const label of ["账号", "模板", "作词", "生成", "上传", "状态", "说明", "明细"]) {
    const span = document.createElement("span");
    span.textContent = label;
    head.append(span);
  }
  table.append(head);

  for (const item of queue?.items || []) {
    const row = document.createElement("div");
    row.className = `pipeline-row pipeline-queue-row${
      item.account_id === state.selectedPipelineDetailAccountId ? " is-selected" : ""
    }`;
    const cells = [
      item.account_name,
      item.template_name,
      pipelineStageProgress(item, "lyrics"),
      pipelineStageProgress(item, "generation"),
      pipelineStageProgress(item, "upload"),
      statusLabels[item.status] || item.status,
      item.error || "-",
    ];
    for (const cell of cells) {
      const span = document.createElement("span");
      span.textContent = cell;
      span.title = String(cell);
      row.append(span);
    }
    const detail = document.createElement("button");
    detail.type = "button";
    detail.className = "button icon-button";
    detail.textContent = "查看";
    detail.disabled = !item.run_id && !item.pipeline_snapshot;
    detail.dataset.pipelineDetail = item.account_id;
    row.append(detail);
    table.append(row);
  }
  if (!queue) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<strong>暂无队列记录</strong><p>勾选账号后开始执行。</p>";
    table.append(empty);
  }

  const finished = (queue?.items || []).filter((item) => ["completed", "failed", "stopped"].includes(item.status)).length;
  elements["pipeline-queue-caption"].textContent = queue
    ? `${queue.day} · ${statusLabels[queue.status] || queue.status} · 完成 ${finished}/${queue.items.length}`
    : "勾选 1 个账号为单账号执行，勾选多个账号为串联执行";
}

function renderPipelinePanel() {
  const run = selectedPipelineDetailRun();
  const busy = pipelineWorkflowBusy();
  elements["pipeline-ai-created"].disabled = busy;
  elements["pipeline-rejected-action"].disabled = busy;
  elements["pipeline-pause"].disabled = busy;
  const selectedCount = elements["pipeline-queue-list"].querySelectorAll("[data-queue-account]:checked").length;
  elements["pipeline-start"].disabled = !selectedCount || busy || isRunning() || uploadRunning();
  elements["pipeline-resume"].hidden = state.pipelineQueue?.status !== "waiting_user";
  elements["pipeline-stop"].disabled = !busy;
  elements["pipeline-refresh"].disabled = (!state.pipelineQueue && !run) || busy || isRunning() || uploadRunning();

  const stageLabels = {
    lyrics: "AI 作词",
    generation: "生成 / 导出 / 下载",
    pre_upload: "上传前确认",
    upload: "上传发布",
    report: "运行报告",
  };
  const statusLabels = {
    running: "运行中",
    waiting_user: "等待确认",
    completed: "已完成",
    failed: "失败",
    stopped: "已停止",
  };
  const finishedSongs = (run?.songs || []).filter((song) =>
    song.lyrics_status === "failed"
      || song.generation_status === "failed"
      || ["completed", "failed", "stopped"].includes(song.upload_status)
  ).length;
  const failedSongs = (run?.songs || []).filter((song) =>
    [song.lyrics_status, song.generation_status, song.upload_status].includes("failed")
  ).length;
  elements["pipeline-caption"].textContent = run
    ? `${run.account_name} · ${run.day} · 模型 ${run.model_name || "自动"} · ${statusLabels[run.status] || run.status} · ${stageLabels[run.stage] || run.stage} · 完成 ${finishedSongs}/${run.songs.length} · 失败 ${failedSongs}`
    : `AI 作词 → 生成下载 → 上传发布 · 模型 ${state.generationModel || "自动"}`;

  document.querySelectorAll("#pipeline-stage-strip [data-stage]").forEach((item) => {
    const generationDone = run?.stage === "upload" && item.dataset.stage === "generation";
    item.classList.toggle("is-active", Boolean(run && (item.dataset.stage === run.stage || generationDone)));
  });

  const table = elements["pipeline-table"];
  table.querySelectorAll(".pipeline-row:not(.pipeline-head)").forEach((node) => node.remove());
  elements["pipeline-empty"].classList.toggle("is-hidden", Boolean(run?.songs?.length));
  const stateLabels = {
    pending: "待处理",
    completed: "完成",
    failed: "失败",
    running: "运行中",
    stopped: "停止",
  };
  for (const song of run?.songs || []) {
    const row = document.createElement("div");
    row.className = "pipeline-row";
    const cells = [
      song.song_name || "-",
      stateLabels[song.lyrics_status] || song.lyrics_status || "-",
      stateLabels[song.generation_status] || song.generation_status || "-",
      song.upload_removed ? "已剔除" : (stateLabels[song.upload_status] || song.upload_status || "-"),
      song.error || (song.output_path || "-"),
    ];
    for (const cell of cells) {
      const span = document.createElement("span");
      span.textContent = cell;
      span.title = String(cell);
      row.append(span);
    }
    table.append(row);
  }
  renderPipelineQueue();
}

async function loadPipelineRun() {
  const reloadId = state.accountReloadId;
  const accountId = state.accountId;
  const params = new URLSearchParams({ day: todayValue() });
  const queueActive = Boolean(
    state.pipelineQueue
    && ["running", "waiting_user"].includes(state.pipelineQueue.status)
  );
  if (accountId && !queueActive) params.set("account_id", accountId);
  state.pipelineRun = await api(`/api/pipeline/runs/current?${params}`).catch(() => null);
  if (accountStateIsStale(reloadId, accountId)) return;
  const signature = state.pipelineRun
    ? `${state.pipelineRun.run_id}:${state.pipelineRun.updated_at}`
    : "";
  if (
    state.pipelineRun
    && !pipelineWorkflowBusy()
    && state.pipelineSyncedSignature !== signature
  ) {
    state.pipelineSyncedSignature = signature;
    try {
      state.pipelineRun = await api("/api/pipeline/runs/refresh", { method: "POST" });
      if (accountStateIsStale(reloadId, accountId)) return;
      state.pipelineSyncedSignature = `${state.pipelineRun.run_id}:${state.pipelineRun.updated_at}`;
    } catch {}
  }
  renderPipelinePanel();
  renderControls();
}

async function loadPipelineQueueOptions() {
  const reloadId = state.accountReloadId;
  const payload = await api("/api/pipeline/queue/options").catch(() => ({ accounts: [] }));
  if (accountStateIsStale(reloadId, state.accountId)) return;
  state.pipelineQueueOptions = payload.accounts || [];
  const optionIds = new Set(state.pipelineQueueOptions.map((option) => option.account_id));
  state.pipelineQueueOrder = [
    ...state.pipelineQueueOrder.filter((accountId) => optionIds.has(accountId)),
    ...state.pipelineQueueOptions.map((option) => option.account_id).filter((accountId) => !state.pipelineQueueOrder.includes(accountId)),
  ];
  state.pipelineQueueOptions.sort((
    first,
    second,
  ) => state.pipelineQueueOrder.indexOf(first.account_id) - state.pipelineQueueOrder.indexOf(second.account_id));
  if (!state.selectedPipelineQueueAccounts.size && state.accountId) {
    state.selectedPipelineQueueAccounts = new Set([state.accountId]);
  } else {
    state.selectedPipelineQueueAccounts = new Set(
      [...state.selectedPipelineQueueAccounts].filter((accountId) => optionIds.has(accountId)),
    );
  }
  renderPipelinePanel();
}

async function loadPipelineQueue() {
  const reloadId = state.accountReloadId;
  const previousQueueId = state.pipelineQueue?.queue_id || "";
  const params = new URLSearchParams({ day: todayValue() });
  state.pipelineQueue = await api(`/api/pipeline/queue/runs/current?${params}`).catch(() => null);
  if (accountStateIsStale(reloadId, state.accountId)) return;
  if ((state.pipelineQueue?.queue_id || "") !== previousQueueId) {
    state.selectedPipelineDetailAccountId = "";
    state.pipelineDetailPinned = false;
  }
  renderPipelinePanel();
  renderControls();
}

async function refreshPipelineRun() {
  state.pipelineRun = await api("/api/pipeline/runs/refresh", { method: "POST" });
  state.pipelineSyncedSignature = `${state.pipelineRun.run_id}:${state.pipelineRun.updated_at}`;
  renderPipelinePanel();
  renderControls();
}

function syncPipelineAfterSingleStage(run) {
  const terminalStatuses = new Set(["completed", "failed", "stopped", "generation_limit"]);
  if (!run || !terminalStatuses.has(run.status)) return;
  if (!state.pipelineRun) return;
  if (
    state.pipelineRun.account_id !== run.account_id
    || state.pipelineRun.day !== run.day
  ) return;
  refreshPipelineRun().catch(() => {});
}

function renderUploads() {
  const files = state.uploads?.files || [];
  const uploadedFiles = state.uploads?.uploaded_files || [];
  const allFiles = [
    ...files.map((file) => ({ ...file, uploaded: false })),
    ...uploadedFiles.map((file) => ({ ...file, uploaded: true })),
  ];
  const dailyLimit = Number(state.uploads?.daily_limit || 10);
  const dailyUsed = Number(
    state.uploads?.daily_used ?? uploadedFiles.length,
  );
  const remaining = Number(
    state.uploads?.remaining_uploads ?? Math.max(0, dailyLimit - dailyUsed),
  );
  const limit = Math.min(Number(state.uploads?.batch_size || dailyLimit), remaining);
  const selectedCount = files.filter((file) => state.selectedUploads.has(file.file_name)).length;
  elements["upload-table"].querySelectorAll(".upload-row:not(.upload-head)").forEach((node) => node.remove());
  elements["upload-empty"].classList.toggle("is-hidden", allFiles.length > 0);
  elements["upload-count"].textContent = String(selectedCount);
  elements["upload-limit"].textContent = String(limit);
  elements["retry-uploads"].textContent = uploadedFiles.length
    ? `重新发布 ${uploadedFiles.length} 首`
    : "重新发布";
  elements["retry-rejected-upload"].textContent = files.length
    ? `再次生成发布 ${files.length} 首`
    : "再次生成发布";
  elements["upload-caption"].textContent = state.uploads?.day
    ? `${state.uploads.day} · 待发布 ${selectedCount}/${files.length} · 今日已发布 ${dailyUsed}/${dailyLimit} · 剩余 ${remaining}`
    : "等待成品下载完成";

  for (const file of allFiles) {
    const row = document.createElement("div");
    row.className = "upload-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedUploads.has(file.file_name);
    checkbox.disabled = file.uploaded || remaining <= 0 || uploadRunning() || isRunning()
      || (!state.selectedUploads.has(file.file_name) && selectedCount >= limit);
    checkbox.dataset.uploadFile = file.file_name;
    const name = document.createElement("span");
    name.textContent = file.file_name;
    name.title = file.path;
    const size = document.createElement("span");
    size.textContent = formatSize(file.size);
    const status = document.createElement("span");
    status.innerHTML = file.uploaded
      ? '<span class="state state-success">已发布</span>'
      : remaining <= 0
        ? '<span class="state state-failed">额度用完</span>'
        : '<span class="state state-waiting">待发布</span>';
    row.append(checkbox, name, size, status);
    elements["upload-table"].append(row);
  }
  renderUploadSource();
  renderDashboard();
}

function renderUploadSource() {
  const account = state.accounts.find((item) => item.id === state.accountId);
  if (!account) {
    elements["upload-dir-input"].value = "";
    elements["current-upload-folder"].textContent = "-";
    return;
  }
  if (document.activeElement !== elements["upload-dir-input"]) {
    elements["upload-dir-input"].value = account.output_dir;
  }
  elements["current-upload-folder"].textContent = joinDayFolder(
    elements["upload-dir-input"].value.trim() || account.output_dir,
    todayValue(),
  );
  const dirty = elements["upload-dir-input"].value.trim() !== account.output_dir;
  elements["apply-upload-dir"].classList.toggle("is-dirty", dirty);
}

function renderLyricSource() {
  const account = state.accounts.find((item) => item.id === state.accountId);
  if (!account) {
    elements["lyric-dir-input"].value = "";
    elements["current-lyric-folder"].textContent = "-";
    return;
  }
  if (document.activeElement !== elements["lyric-dir-input"]) {
    elements["lyric-dir-input"].value = account.lyric_dir;
  }
  elements["current-lyric-folder"].textContent = joinDayFolder(
    elements["lyric-dir-input"].value.trim() || account.lyric_dir,
    todayValue(),
  );
  const dirty = elements["lyric-dir-input"].value.trim() !== account.lyric_dir;
  elements["apply-lyric-dir"].classList.toggle("is-dirty", dirty);
  renderLyricWorkspace();
}

function uploadRunning() {
  return Boolean(state.uploadRun && ["running", "paused", "stopping"].includes(state.uploadRun.status));
}

function rememberUploadRun(run) {
  if (!run?.account_id) return;
  state.uploadRuns[run.account_id] = run;
}

function renderUploadRun() {
  const run = state.uploadRun;
  const account = state.accounts.find((item) => item.id === state.accountId);
  const uploadedFiles = state.uploads?.uploaded_files || [];
  const uploadDirDirty = Boolean(account) && elements["upload-dir-input"].value.trim() !== account.output_dir;
  const pipelineBusy = pipelineWorkflowBusy();
  const dailyLimit = Number(state.uploads?.daily_limit || 10);
  const dailyUsed = Number(state.uploads?.daily_used ?? uploadedFiles.length);
  const remaining = Number(
    state.uploads?.remaining_uploads ?? Math.max(0, dailyLimit - dailyUsed),
  );
  elements["start-upload"].disabled = !state.selectedTaskAccounts.size || uploadDirDirty || isRunning() || uploadRunning() || multiStageRunning() || pipelineBusy;
  elements["select-all-uploads"].disabled = isRunning() || uploadRunning() || pipelineBusy;
  elements["clear-upload-selection"].disabled = isRunning() || uploadRunning() || pipelineBusy;
  elements["refresh-uploads"].disabled = uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
  elements["retry-uploads"].disabled = remaining <= 0 || !uploadedFiles.length || uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
  elements["retry-rejected-upload"].disabled = remaining <= 0 || !state.uploads?.files?.length || uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
  elements["apply-upload-dir"].disabled = !state.accountId || isRunning() || uploadRunning() || pipelineBusy;
  elements["upload-ai-created"].disabled = isRunning() || uploadRunning() || pipelineBusy;
  elements["upload-rejected-action"].disabled = isRunning() || uploadRunning() || pipelineBusy;
  elements["stop-upload"].disabled = !uploadRunning();
  const waiting = Boolean(run?.verification_requested && run.status === "running");
  elements["external-verification-note"].hidden = !waiting;
  if (run && run.status === "running") {
    const labels = {
      starting: "准备上传", opening_browser: "打开浏览器", open_publish_page: "打开发布页",
      add_song: `添加歌曲 ${run.processed + 1}/${run.total}`, album_info: "填写专辑和封面",
      wait_uploads: "等待全部文件上传完成",
      authorization: "填写授权信息",
      waiting_verification_code: "等待手机验证码",
      waiting_external_verification_code: "等待你在平台输入验证码",
      submitting_verification_code: "提交验证码", done: "发布完成",
      remove_noncompliant_songs: "剔除不及格歌曲",
      regenerating_songs: "按歌词重新生成歌曲",
      replace_noncompliant_songs: "寻找并导出第二版本",
      reupload_replaced_songs: "重新上传替换歌曲",
      replace_noncompliant_failed: "第二版本发布失败",
    };
    elements["upload-caption"].textContent = labels[run.step] || run.step;
  } else if (run?.status === "completed") {
    elements["upload-caption"].textContent = run.replaced_titles?.length
      ? `发布完成；已自动替换 ${run.replaced_titles.length} 首`
      : "发布完成";
  } else if (run?.status === "partial_failed") {
    elements["upload-caption"].textContent = run.error || "部分歌曲第二版本发布失败";
  }
}

function stateLabel(value) {
  const labels = {
    pending: "待处理", running: "处理中", success: "成功", failed: "失败",
    skipped: "已跳过", generation_limit: "生成上限", 解析失败: "解析失败",
    download_failed: "下载失败", export_failed: "导出失败",
    lyric_unmatched: "匹配失败", 导出失败: "导出失败",
  };
  return labels[value] || value || "待处理";
}

function stepLabel(value) {
  const labels = {
    pending: "待处理",
    starting: "准备",
    page_ready: "页面准备",
    fill_inputs: "填写歌词",
    generate: "生成歌曲",
    batch_generate: "批量生成",
    check_limit: "检查上限",
    wait_generation: "等待生成",
    match_lyrics: "匹配歌词",
    match_lyrics_settling: "等待结果刷新",
    enter_editor: "进入编辑器",
    export_song: "导出歌曲",
    find_exported_download: "查找导出文件",
    download_song: "下载歌曲",
    start_redownload: "准备重新处理",
    starting_redownload: "准备重新处理",
    starting_repair: "准备批量修复",
    repair_pending: "等待修复",
    repair_generate: "重新生成",
    manual_required: "需手动处理",
    open_assets: "打开歌曲列表",
    done: "完成",
  };
  return labels[value] || value || "-";
}

function isFailureStatus(value) {
  return [
    "failed",
    "generation_limit",
    "login_required",
    "verification_failed",
    "download_failed",
    "export_failed",
    "lyric_unmatched",
    "解析失败",
    "生成上限",
    "需要登录",
    "歌词校验失败",
    "描述不符合",
    "下载失败",
    "导出失败",
    "生成失败",
    "匹配失败",
    "失败",
  ].includes(value);
}

function canAutoRepair(value) {
  return [
    "failed",
    "download_failed",
    "export_failed",
    "lyric_unmatched",
    "下载失败",
    "导出失败",
    "生成失败",
    "匹配失败",
    "失败",
  ].includes(value);
}

function canAutoRepairSong(song) {
  return song.valid && canAutoRepair(songState(song));
}

function selectedAccountsHaveRepairSongs() {
  return selectedTaskAccounts().some((account) => {
    const songs = state.dashboardSongs[account.id]
      || (account.id === state.accountId ? state.songs : []);
    return songs.some(canAutoRepairSong);
  });
}

function stateTone(value) {
  return isFailureStatus(value) ? "failed" : value;
}

function canRedownload(value) {
  return ["download_failed", "export_failed", "下载失败", "导出失败"].includes(value);
}

function isExportRetry(value) {
  return ["export_failed", "导出失败"].includes(value);
}

function songState(song) {
  if (!song.valid) return "解析失败";
  if (state.current && state.current.account_id === state.accountId) {
    const match = state.current.songs.find((item) => item.file_name === song.file_name);
    if (match) return match.status;
  }
  return song.status || "pending";
}

async function startRedownload(song) {
  if (!state.accountId) return toast("请先选择账号", true);
  if (isRunning() || uploadRunning() || pipelineWorkflowBusy()) {
    return toast("当前有其它任务正在运行", true);
  }
  const action = isExportRetry(songState(song)) ? "重新导出" : "重新下载";
  try {
    state.current = await api("/api/runs/redownload", {
      method: "POST",
      body: JSON.stringify({
        account_id: state.accountId,
        file_name: song.file_name,
        day: todayValue(),
      }),
    });
    state.runStatus = state.current?.status || "";
    syncSongRunState(state.current);
    renderCurrent();
    toast(`已开始${action}《${song.song_name || song.file_name}》`);
  } catch (error) {
    toast(error.message, true);
  }
}

function renderSongs() {
  const table = elements["song-table"];
  table.querySelectorAll(".song-row:not(.song-head)").forEach((node) => node.remove());
  elements["queue-empty"].classList.toggle("is-hidden", state.songs.length > 0);
  elements["queue-empty"].querySelector("strong").textContent = state.accounts.length ? "暂无歌词" : "请先创建账号";

  for (const song of state.songs) {
    const row = document.createElement("div");
    row.className = `song-row${state.selected.has(song.file_name) ? " is-selected" : ""}`;
    row.dataset.file = song.file_name;
    const status = songState(song);
    const progress = state.current?.account_id === state.accountId
      ? state.current.songs.find((item) => item.file_name === song.file_name)
      : song;
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
    stateSpan.innerHTML = `<span class="state state-${stateTone(status)}">${stateLabel(status)}</span>`;
    row.append(stateSpan);
    const step = document.createElement("span");
    step.textContent = stepLabel(
      progress?.current_step || (song.error ? "解析" : "-")
    );
    step.title = song.error || progress?.error || "";
    row.append(step);
    const retry = document.createElement("span");
    retry.textContent = progress?.attempts || 0;
    row.append(retry);
    const actions = document.createElement("span");
    if (canRedownload(status)) {
      const redownload = document.createElement("button");
      redownload.type = "button";
      redownload.className = "button song-action-button";
      redownload.textContent = isExportRetry(status) ? "重新导出" : "重新下载";
      redownload.dataset.redownload = song.file_name;
      redownload.disabled = isRunning() || uploadRunning() || pipelineWorkflowBusy();
      redownload.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        void startRedownload(song);
      });
      actions.append(redownload);
    }
    row.append(actions);
    row.addEventListener("click", (event) => {
      if (event.target.closest("input, button, a")) return;
      if (checkbox.disabled) return;
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    });
    table.append(row);
  }

  table.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selected.add(checkbox.dataset.file);
      else state.selected.delete(checkbox.dataset.file);
      checkbox.closest(".song-row")?.classList.toggle("is-selected", checkbox.checked);
      renderMetrics();
    });
  });
  renderMetrics();
}

function renderMetrics() {
  const running = state.songs.filter((song) => songState(song) === "pending" || songState(song) === "running").length;
  const statuses = state.songs.map(songState);
  elements["metric-pending"].textContent = String(running);
  elements["metric-success"].textContent = String(statuses.filter((status) => status === "success" || status === "skipped").length);
  elements["metric-skip"].textContent = String(statuses.filter((status) => status === "skipped").length);
  elements["metric-fail"].textContent = String(statuses.filter(isFailureStatus).length);
  elements["metric-step"].textContent = state.current?.account_id === state.accountId
    ? stepLabel(state.current.current_step)
    : "-";
  renderDashboard();
}

function renderControls() {
  const running = isRunning();
  const pipelineBusy = pipelineWorkflowBusy();
  for (const id of ["account-new", "account-cancel", "account-copy", "select-all", "select-failed", "repair-run", "refresh-songs", "start-run"]) {
    elements[id].disabled = running || pipelineBusy || multiStageRunning();
  }
  elements["account-copy"].disabled = running || pipelineBusy || !state.accountId;
  elements["pause-run"].disabled = !running || state.current?.status !== "running";
  elements["resume-run"].disabled = !running || state.current?.status !== "paused";
  elements["stop-run"].disabled = !running && !multiStageRunning();
  elements["fresh-run"].disabled = running;
  const modelLocked = running || pipelineBusy;
  renderGenerationModelControls(modelLocked);
  const account = state.accounts.find((item) => item.id === state.accountId);
  const lyricDirDirty = Boolean(account) && elements["lyric-dir-input"].value.trim() !== account.lyric_dir;
  elements["apply-lyric-dir"].disabled = running || pipelineBusy || !state.accountId;
  elements["refresh-songs"].disabled = running || pipelineBusy || lyricDirDirty;
  elements["repair-run"].disabled = (
    running
    || uploadRunning()
    || pipelineBusy
    || lyricDirDirty
    || !selectedAccountsHaveRepairSongs()
  );
  if (lyricDirDirty || pipelineBusy || !state.selectedTaskAccounts.size) elements["start-run"].disabled = true;
  elements["account-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  elements["settings-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  const aiConfigBusy = running || uploadRunning() || multiStageRunning() || pipelineWorkflowBusy();
  elements["ai-settings-form"].querySelectorAll("input").forEach((input) => input.disabled = aiConfigBusy);
  elements["test-ai-settings"].disabled = aiConfigBusy;
  document.querySelectorAll("[data-test-ai-config]").forEach((button) => {
    button.disabled = aiConfigBusy || Object.values(state.aiApiChecks).some((item) => item.status === "checking");
  });
  document.querySelectorAll("[data-edit-ai-config]").forEach((button) => button.disabled = aiConfigBusy);
  elements["ai-config-cancel"].disabled = aiConfigBusy;
  elements["save-settings"].disabled = aiConfigBusy;
  document.querySelectorAll("[data-edit-account]").forEach((button) => button.disabled = running);
  document.querySelectorAll("[data-delete-account]").forEach((button) => button.disabled = running || uploadRunning());
  document.querySelectorAll("[data-login-account]").forEach((button) => button.disabled = running || uploadRunning());
  document.querySelectorAll("[data-close-browser-account]").forEach((button) => button.disabled = running || uploadRunning());
  renderTaskAccounts();
  renderUploadRun();
  renderLyricControls();
  renderPipelinePanel();
  syncAiProviderSelect();
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

function syncSongRunState(run) {
  if (!run || run.account_id !== state.accountId) return;
  const progressByFile = new Map(run.songs.map((song) => [song.file_name, song]));
  for (const song of state.songs) {
    const progress = progressByFile.get(song.file_name);
    if (!progress) continue;
    for (const key of ["status", "current_step", "attempts", "error", "output_path"]) {
      if (progress[key] !== undefined) song[key] = progress[key];
    }
    if (progress.song_name) song.song_name = progress.song_name;
  }
}

function applyCurrentRun(run, { immediate = false } = {}) {
  const previousStatus = state.runStatus;
  rememberGenerationRun(run);
  state.current = run;
  state.runStatus = run?.status || "";
  syncSongRunState(run);
  renderCurrent();

  const terminalStatuses = new Set(["completed", "failed", "stopped", "generation_limit"]);
  if (!run?.run_id || !terminalStatuses.has(run.status) || state.notifiedRunId === run.run_id) return;
  if (!immediate && !["running", "paused", "stopping"].includes(previousStatus)) return;

  state.notifiedRunId = run.run_id;
  if (run.status === "completed") {
    const allSkipped = run.skipped_count === run.songs.length && run.songs.length > 0;
    toast(allSkipped
      ? `任务已结束：${run.skipped_count} 首已处理过，无需重复操作`
      : `任务已结束：成功 ${run.success_count}，跳过 ${run.skipped_count}，失败 ${run.failure_count}`);
    return;
  }

  const labels = {
    failed: `任务已结束：失败 ${run.failure_count} 首`,
    stopped: "任务已结束：已停止",
    generation_limit: "任务已结束：达到生成上限",
  };
  toast(labels[run.status] || "任务已结束", run.status !== "completed");
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
  if (!state.selectedTaskAccounts.size && state.accountId) {
    state.selectedTaskAccounts = new Set([state.accountId]);
  }
  if (state.editingAccountId && !state.accounts.some((account) => account.id === state.editingAccountId)) {
    state.editingAccountId = "";
    state.accountEditorOpen = false;
  }
  renderAccounts();
  const account = state.accounts.find((item) => item.id === state.accountId);
  fillAccountForm(account);
  await reloadAccountWorkspace();
  void loadDashboardSongs().catch(() => {});
}

async function reloadAccountWorkspace() {
  const reloadId = ++state.accountReloadId;
  const accountId = state.accountId;
  state.songs = [];
  state.selected = new Set();
  state.pipelineRun = null;
  state.pipelineSyncedSignature = "";
  if (!runMatchesCurrentAccount(state.current)) {
    state.current = null;
    state.runStatus = "";
  }
  const runningRun = liveGenerationRun(accountId);
  if (runningRun && !state.current) {
    state.current = runningRun;
    state.runStatus = runningRun.status;
  }
  if (!runMatchesCurrentAccount(state.uploadRun)) state.uploadRun = null;
  renderPipelinePanel();
  renderCurrent();
  renderUploadRun();

  const isStale = () => reloadId !== state.accountReloadId;
  if (accountId) await loadSongs().catch(() => renderSongs());
  else renderSongs();
  if (isStale()) return;

  await loadLyricTemplates().catch(() => {});
  if (isStale()) return;

  await loadUploads().catch(() => {
    state.uploads = [];
    renderUploads();
  });
  if (isStale()) return;

  await loadPipelineRun();
  if (isStale()) return;

  await loadPipelineQueueOptions();
  if (isStale()) return;

  await loadPipelineQueue();
  if (isStale()) return;

  await loadCurrent().catch(() => {});
  if (isStale()) return;

  await loadUploadRun();
  if (isStale()) return;

  renderControls();
  renderTaskStatus();
}

async function loadSongs() {
  const reloadId = state.accountReloadId;
  const accountId = state.accountId;
  if (!accountId) return;
  const account = state.accounts.find((item) => item.id === accountId);
  const day = todayValue();
  state.songs = await api(`/api/accounts/${accountId}/songs?day=${encodeURIComponent(day)}`);
  if (accountStateIsStale(reloadId, accountId)) return;
  state.selected = new Set(state.songs.filter((song) => song.valid).map((song) => song.file_name));
  elements["queue-caption"].textContent = `${account.account_name} · ${day} · ${state.songs.length} 个文件`;
  renderLyricSource();
  renderSongs();
  renderControls();
}

async function loadDashboardSongs() {
  if (!state.accounts.length) {
    state.dashboardSongs = {};
    renderDashboard();
    return;
  }

  const day = todayValue();
  const entries = await Promise.all(state.accounts.map(async (account) => {
    const songs = await api(`/api/accounts/${account.id}/songs?day=${encodeURIComponent(day)}`).catch(() => null);
    return [account.id, songs || []];
  }));
  if (day !== todayValue()) return;
  state.dashboardSongs = Object.fromEntries(entries);
  renderDashboard();
  renderTaskAccounts();
}

async function loadStageAccountData() {
  if (!state.accounts.length) {
    state.dashboardSongs = {};
    state.accountTemplates = {};
    state.stageUploads = {};
    renderTaskAccounts();
    return;
  }

  const requests = [loadDashboardSongs()];
  if (state.stage === "lyrics") {
    requests.push(Promise.all(state.accounts.map(async (account) => {
      const payload = await api(`/api/accounts/${account.id}/lyric/templates`).catch(() => ({ templates: [] }));
      return [account.id, payload.templates || []];
    })).then((entries) => {
      state.accountTemplates = Object.fromEntries(entries);
    }));
  }
  if (state.stage === "upload" || state.stage === "pipeline") {
    requests.push(Promise.all(state.accounts.map(async (account) => {
      const payload = await api(`/api/accounts/${account.id}/uploads?day=${encodeURIComponent(todayValue())}`).catch(() => null);
      return [account.id, payload];
    })).then((entries) => {
      state.stageUploads = Object.fromEntries(entries);
    }));
  }
  await Promise.allSettled(requests);
  renderTaskAccounts();
}

async function loadUploads() {
  const reloadId = state.accountReloadId;
  const accountId = state.accountId;
  if (!accountId) {
    state.uploads = [];
    renderUploads();
    return;
  }
  try {
    state.uploads = await api(`/api/accounts/${accountId}/uploads?day=${encodeURIComponent(todayValue())}`);
  } catch {
    state.uploads = [];
  }
  if (accountStateIsStale(reloadId, accountId)) return;
  const files = state.uploads?.files || [];
  const dailyLimit = Number(state.uploads?.daily_limit || 10);
  const dailyUsed = Number(
    state.uploads?.daily_used ?? (state.uploads?.uploaded_files || []).length,
  );
  const remaining = Number(
    state.uploads?.remaining_uploads ?? Math.max(0, dailyLimit - dailyUsed),
  );
  const limit = Math.min(Number(state.uploads?.batch_size || dailyLimit), remaining);
  if (state.uploadSelectionAccountId !== state.accountId) {
    state.uploadSelectionAccountId = state.accountId;
    state.uploadSelectionTouched = false;
    state.selectedUploads = new Set(files.slice(0, limit).map((file) => file.file_name));
  } else {
    const available = new Set(files.map((file) => file.file_name));
    const selected = [...state.selectedUploads].filter((name) => available.has(name));
    state.selectedUploads = new Set(
      files.filter((file) => selected.includes(file.file_name)).slice(0, limit)
        .map((file) => file.file_name),
    );
    if (!state.uploadSelectionTouched) {
      for (const file of files) {
        if (state.selectedUploads.size >= limit) break;
        state.selectedUploads.add(file.file_name);
      }
    }
  }
  renderUploads();
}

async function loadUploadRun() {
  const reloadId = state.accountReloadId;
  const accountId = state.accountId;
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  const query = params.toString();
  state.uploadRun = await api(`/api/uploads/runs/current${query ? `?${query}` : ""}`).catch(() => null);
  if (accountStateIsStale(reloadId, accountId)) return;
  renderUploadRun();
  renderTaskStatus();
}

async function loadMultiStage() {
  state.multiQueue = await api("/api/multi-stage/runs/current").catch(() => null);
  syncLyricQueueSnapshot(state.multiQueue);
  renderTaskAccounts();
  renderTaskStatus();
  renderControls();
}

function formatMonitoringValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return Number.isInteger(number) ? number.toLocaleString("zh-CN") : number.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
  });
}

function formatMonitoringDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[1]}/${match[2]}/${match[3]}` : String(value || "-");
}

function formatMonitoringDateTime(value) {
  const raw = String(value || "");
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) return raw || "-";
  const [, iso_date, clock] = match;
  const [, month, day] = iso_date.split("-");
  return month && day ? `${month}/${day} ${clock}` : `${formatMonitoringDate(iso_date)} ${clock}`;
}

function renderMonitoring() {
  const payload = state.monitoringStatistics;
  const accounts = payload?.accounts || [];
  const allRecords = payload?.records || [];
  const records = state.monitoringViewAccountId === "all"
    ? allRecords
    : allRecords.filter((record) => record.account_id === state.monitoringViewAccountId);
  const snapshots = payload?.snapshots || [];
  const accountIds = new Set(snapshots.map((snapshot) => snapshot.account_id).filter(Boolean));
  const completed = snapshots.filter((snapshot) => snapshot.status === "completed").length;
  const abnormal = snapshots.filter((snapshot) => snapshot.status !== "completed").length;
  const dates = snapshots.map((snapshot) => snapshot.data_end_date).filter(Boolean);
  const range = dates.length
    ? `${formatMonitoringDate([...dates].sort().at(0))} - ${formatMonitoringDate([...dates].sort().at(-1))}`
    : "-";

  const collection = state.monitoringCollection;
  const collectionRunning = Boolean(collection && ["running", "stopping"].includes(collection.status));
  const collectionText = collectionRunning
    ? ` · 采集 ${collection.items.filter((item) => item.status === "completed").length}/${collection.items.length}`
    : "";
  const viewName = state.monitoringViewAccountId === "all"
    ? "全部账号"
    : state.accounts.find((account) => account.id === state.monitoringViewAccountId)?.account_name || "当前账号";
  const nextAutomatic = state.monitoringSettings?.next_automatic_at
    ? ` · 下次自动 ${formatMonitoringDateTime(state.monitoringSettings.next_automatic_at)}`
    : "";
  elements["monitoring-caption"].textContent = `00/04/08/12/16/20 点自动采集 · 上传后近 7 天采集 · 数据截止 ${range} · ${viewName}${collectionText}${nextAutomatic}`;
  elements["monitoring-account-count"].textContent = String(accounts.length);
  elements["monitoring-collection-count"].textContent = String(snapshots.length);
  elements["monitoring-success-count"].textContent = String(completed);
  elements["monitoring-failed-count"].textContent = String(abnormal);
  elements["collect-monitoring"].disabled = collectionRunning
    || state.monitoringCollectionLoading
    || !state.monitoringSelectedAccountIds.size;
  elements["stop-monitoring"].hidden = !collectionRunning;

  const accountList = elements["monitoring-account-list"];
  accountList.innerHTML = "";
  state.accounts.forEach((account) => {
    const selected = state.monitoringSelectedAccountIds.has(account.id);
    const item = document.createElement("label");
    item.className = `monitoring-account-item${selected ? " is-selected" : ""}`;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected;
    checkbox.dataset.monitoringAccount = account.id;
    checkbox.disabled = collectionRunning;
    const name = document.createElement("span");
    name.textContent = account.account_name;
    const port = document.createElement("small");
    port.textContent = `端口 ${account.chrome_debug_port}`;
    item.append(checkbox, name, port);
    accountList.append(item);
  });
  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "monitoring-account-empty";
    empty.textContent = "暂无账号";
    accountList.append(empty);
  }

  const viewList = elements["monitoring-view-list"];
  viewList.innerHTML = "";
  [
    { id: "all", name: "全部" },
    ...state.accounts.map((account) => ({ id: account.id, name: account.account_name })),
  ].forEach((view) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `monitoring-view-button${state.monitoringViewAccountId === view.id ? " is-active" : ""}`;
    button.textContent = view.name;
    button.dataset.monitoringView = view.id;
    viewList.append(button);
  });

  const table = elements["monitoring-table"];
  table.querySelectorAll(".monitoring-row:not(.monitoring-head)").forEach((node) => node.remove());
  records.forEach((record) => {
    const row = document.createElement("div");
    row.className = "monitoring-row";
    const cells = [
      formatMonitoringDateTime(record.collected_at),
      formatMonitoringDate(record.date),
      record.account_name || "-",
      formatMonitoringValue(record.qishui_heat_index),
      formatMonitoringValue(record.qishui_play_count),
      formatMonitoringValue(record.qishui_paid_user_play_index),
      formatMonitoringValue(record.qishui_search_play_index),
      formatMonitoringValue(record.available_balance_yuan),
    ];
    cells.forEach((value) => {
      const cell = document.createElement("span");
      cell.textContent = value;
      row.append(cell);
    });
    table.append(row);
  });
  elements["monitoring-empty"].hidden = records.length > 0;

  const statusList = elements["monitoring-status-list"];
  statusList.innerHTML = "";
  const abnormalSnapshots = snapshots.filter((snapshot) => snapshot.status !== "completed");
  const statusEntries = [
    ...abnormalSnapshots.map((snapshot) => ({
      key: `snapshot-${snapshot.snapshot_id}`,
      label: `${snapshot.account_name} · ${formatMonitoringDateTime(snapshot.collected_at)} · ${snapshot.status === "failed" ? "采集失败" : "未采集"}`,
      detail: snapshot.error || "",
    })),
    ...(collectionRunning ? collection.items
      .filter((item) => item.status !== "completed")
      .map((item) => ({
        key: `collection-${item.item_id}`,
        label: `${item.account_name} · ${item.status === "running" ? "采集中" : item.status === "stopping" ? "停止中" : "等待采集"}`,
        detail: item.error || "",
      })) : []),
  ];
  statusList.hidden = statusEntries.length === 0;
  statusEntries.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "monitoring-status-item";
    const label = document.createElement("strong");
    label.textContent = entry.label;
    const detail = document.createElement("span");
    detail.textContent = entry.detail;
    item.append(label, detail);
    statusList.append(item);
  });
}

async function loadMonitoringStatistics() {
  if (state.monitoringLoading) return;
  state.monitoringLoading = true;
  try {
    state.monitoringStatistics = await api("/api/monitoring/statistics?days=7");
  } finally {
    state.monitoringLoading = false;
  }
  renderMonitoring();
}

async function loadMonitoringSettings() {
  const settings = await api("/api/monitoring/settings");
  const accountIds = new Set(state.accounts.map((account) => account.id));
  state.monitoringSettings = settings;
  state.monitoringSelectedAccountIds = new Set(
    (settings.account_ids || []).filter((accountId) => accountIds.has(accountId)),
  );
  renderMonitoring();
}

async function saveMonitoringSettings() {
  const previous = state.monitoringSettings;
  const accountIds = [...state.monitoringSelectedAccountIds];
  try {
    state.monitoringSettings = await api("/api/monitoring/settings", {
      method: "PUT",
      body: JSON.stringify({ account_ids: accountIds }),
    });
  } catch (error) {
    state.monitoringSettings = previous;
    toast(`保存采集账号失败: ${error.message}`, true);
  }
  renderMonitoring();
}

async function loadMonitoringCollection() {
  if (state.monitoringCollectionLoading) return;
  const previous = state.monitoringCollection;
  const requestSeq = state.monitoringCollectionRequestSeq + 1;
  state.monitoringCollectionRequestSeq = requestSeq;
  state.monitoringCollectionLoading = true;
  let next = null;
  try {
    next = await api("/api/monitoring/collections/current");
  } catch (error) {
    if (requestSeq === state.monitoringCollectionRequestSeq && !previous) {
      state.monitoringCollection = null;
    }
    return;
  } finally {
    state.monitoringCollectionLoading = false;
  }
  if (requestSeq !== state.monitoringCollectionRequestSeq) return;
  state.monitoringCollection = next;
  const wasRunning = Boolean(previous && ["running", "stopping"].includes(previous.status));
  const isRunning = Boolean(
    state.monitoringCollection && ["running", "stopping"].includes(state.monitoringCollection.status),
  );
  if (wasRunning && !isRunning) {
    await loadMonitoringStatistics().catch(() => {});
    const failed = state.monitoringCollection?.items?.filter((item) => item.status === "failed") || [];
    toast(failed.length ? `采集完成，${failed.length} 个账号失败` : "监控数据采集完成", failed.length > 0);
  }
  renderMonitoring();
}

function selectedTaskAccounts() {
  const selected = state.selectedTaskAccounts;
  return state.accounts.filter((account) => selected.has(account.id));
}

async function buildGenerationQueueItems(accounts) {
  const items = [];
  const skipped = [];
  for (const account of accounts) {
    const songs = await api(`/api/accounts/${account.id}/songs?day=${encodeURIComponent(todayValue())}`);
    const valid = songs.filter((song) => song.valid);
    const files = account.id === state.accountId && state.selected.size
      ? valid.filter((song) => state.selected.has(song.file_name)).map((song) => song.file_name)
      : valid.map((song) => song.file_name);
    if (!files.length) {
      skipped.push({ id: account.id, name: account.account_name });
      continue;
    }
    items.push({ account_id: account.id, song_files: files });
  }
  return { items, skipped };
}

async function buildUploadQueueItems() {
  const items = [];
  for (const account of selectedTaskAccounts()) {
    const batch = await api(`/api/accounts/${account.id}/uploads?day=${encodeURIComponent(todayValue())}`);
    const remaining = Math.max(0, Number(batch.remaining_uploads || 0));
    const limit = Math.min(Number(batch.batch_size || 10), remaining);
    const files = batch.files || [];
    let names = files.slice(0, limit).map((file) => file.file_name);
    if (account.id === state.accountId && state.selectedUploads.size) {
      const selected = new Set(state.selectedUploads);
      names = files.filter((file) => selected.has(file.file_name)).slice(0, limit)
        .map((file) => file.file_name);
    }
    if (!names.length) {
      toast(`${account.account_name} 没有可上传成品或额度已用完，已跳过`, true);
      continue;
    }
    items.push({ account_id: account.id, file_names: names });
  }
  return items;
}

async function buildLyricQueueItems() {
  const items = [];
  for (const account of selectedTaskAccounts()) {
    const payload = await api(`/api/accounts/${account.id}/lyric/templates`);
    const templates = payload.templates || [];
    const template = account.id === state.accountId
      ? templates.find((item) => item.id === state.selectedLyricTemplateId) || templates[0]
      : templates[0];
    if (!template) {
      toast(`${account.account_name} 没有作词模板，已跳过`, true);
      continue;
    }
    items.push({ account_id: account.id, template_id: template.id });
  }
  return items;
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  state.lyricSystemPrompt = state.settings.ai_system_prompt;
  for (const key of Object.keys(state.settings)) {
    if (elements["settings-form"].elements[key]) {
      elements["settings-form"].elements[key].value = state.settings[key];
    }
  }
  if (!aiApiConfigs().length) {
    state.aiConfigEditorOpen = true;
    state.editingAIProviderId = "";
    fillAiApiForm(null);
  }
  renderSettingsTabs();
}

async function loadLyricTemplates() {
  const reloadId = state.accountReloadId;
  const accountId = state.accountId;
  if (!accountId) {
    state.lyricTemplates = [];
    state.lyricResults = [];
    state.selectedLyricTemplateId = "";
    renderLyricWorkspace();
    return;
  }
  const payload = await api(`/api/accounts/${accountId}/lyric/templates`);
  if (accountStateIsStale(reloadId, accountId)) return;
  state.lyricSystemPrompt = payload.system_prompt;
  const previousTemplateId = state.selectedLyricTemplateId;
  state.lyricTemplates = payload.templates;
  state.lyricResults = [];
  state.selectedLyricTemplateId = state.lyricTemplates.some((template) => template.id === previousTemplateId)
    ? previousTemplateId
    : "";
  renderLyricWorkspace();
}

async function loadCurrent() {
  const reloadId = state.accountReloadId;
  const accountId = state.accountId;
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  const query = params.toString();
  const run = await api(`/api/runs/current${query ? `?${query}` : ""}`);
  if (accountStateIsStale(reloadId, accountId)) return;
  applyCurrentRun(run);
}

async function loadLoginBrowser() {
  const current = await api("/api/browser/current").catch(() => null);
  state.loginBrowser = current;
  renderAccountCards();
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
    if (message.type === "multi_stage_status") {
      const wasRunning = multiStageRunning();
      state.multiQueue = message.data;
      syncLyricQueueSnapshot(state.multiQueue);
      renderTaskAccounts();
      renderTaskStatus();
      renderControls();
      if (state.multiQueue?.stage === "lyrics") {
        void loadDashboardSongs().catch(() => {});
      }
      if (state.multiQueue?.stage === "upload") {
        void loadMonitoringStatistics().catch(() => {});
      }
      if (wasRunning && !multiStageRunning()) {
        void loadDashboardSongs().catch(() => {});
        void loadSongs().catch(() => {});
        void loadUploads().catch(() => {});
        void loadPipelineQueueOptions().catch(() => {});
        if (state.multiQueue?.stage === "upload") {
          void loadMonitoringStatistics().catch(() => {});
        }
      }
      return;
    }
    if (message.type === "upload_status") {
      rememberUploadRun(message.data);
      if (runMatchesCurrentAccount(message.data)) {
        state.uploadRun = message.data;
        renderUploadRun();
        renderTaskStatus();
        syncPipelineAfterSingleStage(state.uploadRun);
      } else {
        renderTaskAccounts();
      }
    }
    if (message.type === "pipeline_status") {
      const run = message.data;
      if (runMatchesCurrentAccount(run) && run.day === todayValue()) {
        state.pipelineRun = run;
        state.pipelineSyncedSignature = `${run.run_id}:${run.updated_at}`;
        renderPipelinePanel();
        renderControls();
      }
    }
    if (message.type === "pipeline_queue_status") {
      const queue = message.data;
      if (queue.day === todayValue()) {
        state.pipelineQueue = queue;
        renderPipelinePanel();
        renderControls();
      }
    }
    if (message.type === "status") {
      rememberGenerationRun(message.data);
      if (runMatchesCurrentAccount(message.data)) {
        applyCurrentRun(message.data);
        syncPipelineAfterSingleStage(state.current);
      } else {
        renderTaskAccounts();
      }
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
  if (multiStageRunning()) {
    if (action !== "stop") return toast("多账号队列只支持停止", true);
    try {
      state.multiQueue = await api("/api/multi-stage/runs/stop", { method: "POST" });
      renderTaskAccounts();
      renderTaskStatus();
      renderControls();
      toast("已请求停止多账号队列");
    } catch (error) {
      toast(error.message, true);
    }
    return;
  }
  try {
    state.current = await api("/api/runs/control", { method: "POST", body: JSON.stringify({ action }) });
    renderCurrent();
    toast(action === "pause" ? "已请求暂停" : action === "resume" ? "已继续" : "已请求停止");
  } catch (error) {
    toast(error.message, true);
  }
}

function openGenerationAccountEditor(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account) return;
  state.editingStageAccountId = accountId;
  elements["generation-account-title"].textContent = `修改 · ${account.account_name}`;
  elements["account-model-select"].value = account.model_name || "自动";
  elements["account-singer-select"].value = singerNameForModel(account.model_name, account.singer_name);
  renderAccountSingerVisibility();
  elements["generation-account-form"].hidden = false;
  elements["generation-account-form"].scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function fillLyricTemplateFormForStage(template = null) {
  state.lyricTemplateEditorOpen = true;
  state.editingLyricTemplateId = template?.id || "";
  state.lyricTemplateAccountLocked = true;
  state.selectedTemplateThemes = template ? [...template.themes] : [];
  elements["template-account-select"].value = template?.account_id || state.accountId || "";
  elements["template-name"].value = template?.name || "";
  elements["template-lyric-tone"].value = template?.lyric_tone || "";
  elements["template-song-style"].value = template?.song_style || "";
  elements["template-generation-count"].value = template?.generation_count || 1;
  elements["custom-theme"].value = "";
  renderTemplateOutputLocation();
  renderLyricTemplateEditor();
  elements["lyric-template-form"]?.scrollIntoView({ behavior: "smooth", block: "center" });
  elements["template-name"].focus();
}

async function openLyricAccountEditor(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account) return;
  state.accountId = accountId;
  elements["account-select"].value = accountId;
  state.lyricTemplates = [];
  state.lyricResults = [];
  state.selectedLyricTemplateId = "";
  state.lyricTemplateEditorOpen = false;
  state.editingLyricTemplateId = "";
  state.lyricTemplateAccountLocked = true;
  renderAccounts();
  renderControls();
  state.settingsTab = "prompt";
  state.view = "settings";
  renderView();
  await reloadAccountWorkspace();
  if (state.accountId !== accountId) return;
  const template = state.lyricTemplates[0];
  state.selectedLyricTemplateId = template?.id || "";
  fillLyricTemplateFormForStage(template || null);
  renderLyricWorkspace();
  elements["lyric-template-caption"].textContent = `正在修改 ${account.account_name} 的作词模板`;
  elements["lyric-template-form"]?.scrollIntoView({ behavior: "smooth", block: "center" });
  toast(template ? `正在修改 ${account.account_name} 的模板` : `请为 ${account.account_name} 创建模板`);
}

document.addEventListener("DOMContentLoaded", async () => {
  setupTooltips();
  restoreGenerationModel();
  restoreGenerationSinger();
  renderGenerationModelControls();
  bindEvents();
  renderView();
  await Promise.allSettled([loadHealth(), loadSettings()]);
  await loadAccounts();
  await loadMonitoringSettings().catch(() => {});
  await loadLoginBrowser();
  await Promise.allSettled([
    loadMultiStage(),
    loadStageAccountData(),
    loadMonitoringStatistics(),
    loadMonitoringCollection(),
  ]);
  const recent = await api("/api/logs/recent").catch(() => []);
  for (const event of recent) if (event.type === "log") appendLog(event.data);
  connectSocket();
  setInterval(loadHealth, 5000);
  setInterval(loadLoginBrowser, 5000);
  setInterval(loadUploads, 10000);
  setInterval(loadDashboardSongs, 10000);
  setInterval(loadStageAccountData, 10000);
  setInterval(loadUploadRun, 5000);
  setInterval(loadMultiStage, 5000);
  setInterval(loadMonitoringStatistics, 10000);
  setInterval(loadMonitoringCollection, state.monitoringCollection ? 1000 : 2000);
  setInterval(loadPipelineRun, 5000);
  setInterval(loadPipelineQueue, 5000);
  window.appReady = true;
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
  elements["task-account-list"].addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-task-account]");
    if (!checkbox || checkbox.disabled) return;
    if (checkbox.checked) state.selectedTaskAccounts.add(checkbox.dataset.taskAccount);
    else state.selectedTaskAccounts.delete(checkbox.dataset.taskAccount);
    if (!pipelineWorkflowBusy()) {
      state.selectedPipelineQueueAccounts = new Set(state.selectedTaskAccounts);
    }
    renderTaskAccounts();
    renderControls();
  });

  elements["task-account-list"].addEventListener("click", async (event) => {
    const button = event.target.closest("[data-focus-account]");
    if (!button || button.disabled) return;
    elements["account-select"].value = button.dataset.focusAccount;
    elements["account-select"].dispatchEvent(new Event("change", { bubbles: true }));
  });

  elements["stage-account-table"].addEventListener("change", async (event) => {
    const contractInput = event.target.closest("[data-contract-account]");
    if (contractInput) {
      if (!contractInput.disabled) {
        await saveUploadContractMode(
          contractInput.dataset.contractAccount,
          contractInput.value,
        );
      }
      return;
    }

    const checkbox = event.target.closest("[data-task-account]");
    if (!checkbox || checkbox.disabled) return;
    if (checkbox.checked) state.selectedTaskAccounts.add(checkbox.dataset.taskAccount);
    else state.selectedTaskAccounts.delete(checkbox.dataset.taskAccount);
    if (!pipelineWorkflowBusy()) {
      state.selectedPipelineQueueAccounts = new Set(state.selectedTaskAccounts);
    }
    renderTaskAccounts();
    renderControls();
  });

  elements["stage-account-table"].addEventListener("click", async (event) => {
    const row = event.target.closest("[data-stage-account]");
    const control = event.target.closest("button, input, select, textarea, a");
    if (row && !control && !multiStageRunning() && !isRunning() && !uploadRunning() && !pipelineWorkflowBusy()) {
      const accountId = row.dataset.stageAccount;
      if (state.selectedTaskAccounts.has(accountId)) {
        state.selectedTaskAccounts.delete(accountId);
      } else {
        state.selectedTaskAccounts.add(accountId);
      }
      if (!pipelineWorkflowBusy()) {
        state.selectedPipelineQueueAccounts = new Set(state.selectedTaskAccounts);
      }
      renderTaskAccounts();
      renderControls();
      return;
    }

    const editButton = event.target.closest("[data-edit-stage-account]");
    const focusButton = event.target.closest("[data-focus-account]");
    if (editButton && !editButton.disabled) {
      const accountId = editButton.dataset.editStageAccount;
      if (state.stage === "generation") {
        openGenerationAccountEditor(accountId);
      } else {
        await openLyricAccountEditor(accountId);
      }
      return;
    }
    if (focusButton && !focusButton.disabled) {
      elements["account-select"].value = focusButton.dataset.focusAccount;
      elements["account-select"].dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  elements["generation-account-cancel"].addEventListener("click", () => {
    state.editingStageAccountId = "";
    elements["generation-account-form"].hidden = true;
  });

  elements["account-model-select"].addEventListener("change", renderAccountSingerVisibility);

  elements["generation-account-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    const account = state.accounts.find((item) => item.id === state.editingStageAccountId);
    if (!account) return;
    try {
      const updated = await api(`/api/accounts/${account.id}`, {
        method: "PUT",
        body: JSON.stringify({
          ...account,
          model_name: elements["account-model-select"].value,
          singer_name: singerNameForModel(
            elements["account-model-select"].value,
            elements["account-singer-select"].value,
          ),
        }),
      });
      state.accounts = state.accounts.map((item) => item.id === updated.id ? updated : item);
      if (state.accountId === updated.id) fillAccountForm(updated);
      state.editingStageAccountId = "";
      elements["generation-account-form"].hidden = true;
      renderTaskAccounts();
      toast("生成配置已保存");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["task-account-all"].addEventListener("click", () => {
    state.selectedTaskAccounts = new Set(state.accounts.map((account) => account.id));
    if (!pipelineWorkflowBusy()) {
      state.selectedPipelineQueueAccounts = new Set(state.selectedTaskAccounts);
    }
    renderTaskAccounts();
    renderControls();
  });

  elements["task-account-clear"].addEventListener("click", () => {
    state.selectedTaskAccounts.clear();
    if (!pipelineWorkflowBusy()) {
      state.selectedPipelineQueueAccounts.clear();
    }
    renderTaskAccounts();
    renderControls();
  });

  document.querySelectorAll(".nav-item:not(.is-disabled)").forEach((item) => {
    item.addEventListener("click", () => {
      state.view = item.dataset.view;
      if (item.dataset.stage) state.stage = item.dataset.stage;
      if (state.view === "task" && state.stage === "lyrics") {
        state.stage = "generation";
      }
      renderView();
      if (state.view === "task" || state.view === "lyrics") {
        void loadStageAccountData().catch(() => {});
      }
      if (state.view === "monitoring") {
        void loadMonitoringStatistics().catch(() => {});
      }
    });
  });

  document.querySelectorAll("[data-dashboard-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`.stage[data-stage="${button.dataset.dashboardStage}"]`)?.click();
    });
  });

  document.querySelectorAll("[data-dashboard-view]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`.nav-item[data-view="${button.dataset.dashboardView}"]`)?.click();
    });
  });

  document.querySelectorAll(".stage:not([disabled])").forEach((item) => {
    item.addEventListener("click", () => {
      state.stage = item.dataset.stage;
      if (state.stage === "lyrics") {
        state.view = "lyrics";
      } else {
        state.view = "task";
      }
      if (state.stage === "pipeline") void loadPipelineQueueOptions();
      renderView();
      const panel = document.querySelector({
        lyrics: ".lyric-layout",
        upload: ".upload-panel",
        pipeline: ".pipeline-panel",
      }[state.stage] || ".queue-panel");
      panel?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });

  elements["account-select"].addEventListener("change", async () => {
    state.accountId = elements["account-select"].value;
    renderAccounts();
    renderControls();
    await reloadAccountWorkspace();
  });

  elements["account-new"].addEventListener("click", async () => {
    state.editingAccountId = "";
    state.accountEditorOpen = true;
    const suggested = await api("/api/available-port").catch(() => ({ chrome_debug_port: 9222 }));
    fillAccountForm(null, suggested.chrome_debug_port);
    renderAccountEditor();
    elements["account-form"].account_name.focus();
  });

  elements["account-cancel"].addEventListener("click", () => {
    state.editingAccountId = "";
    state.accountEditorOpen = false;
    fillAccountForm(state.accounts.find((item) => item.id === state.accountId));
    renderAccountEditor();
  });

  elements["account-cards"].addEventListener("click", async (event) => {
    const card = event.target.closest(".account-card");
    if (!card) return;
    const editButton = event.target.closest("[data-edit-account]");
    const deleteButton = event.target.closest("[data-delete-account]");
    const loginButton = event.target.closest("[data-login-account]");
    const closeBrowserButton = event.target.closest("[data-close-browser-account]");
    const button = editButton || deleteButton || loginButton || closeBrowserButton;
    if (button && button.disabled) return;
    const account = state.accounts.find(
      (item) => item.id === (button ? (
        editButton?.dataset.editAccount
        || deleteButton?.dataset.deleteAccount
        || loginButton?.dataset.loginAccount
        || closeBrowserButton?.dataset.closeBrowserAccount
      ) : card.dataset.accountId),
    );
    if (!account) return;

    if (deleteButton) {
      const profileShared = state.accounts.some(
        (item) => item.id !== account.id && item.chrome_profile_dir === account.chrome_profile_dir,
      );
      const confirmed = confirm([
        `确定删除账号“${account.account_name}”吗？`,
        "",
        profileShared ? "该 Chrome 用户目录同时被其它账号使用，只删除这个账号配置。" : "将同时删除：",
        profileShared ? "" : "1. 控制台里的账号配置",
        profileShared ? "" : `2. 绑定的 Chrome 用户目录：${account.chrome_profile_dir}`,
        "",
        "不会删除：歌词、成品音乐、下载目录。",
      ].join("\n"));
      if (!confirmed) return;
      api(`/api/accounts/${account.id}${profileShared ? "" : "?delete_chrome=true"}`, { method: "DELETE" })
        .then(() => loadAccounts())
        .then(() => toast("账号配置已删除"))
        .catch((error) => toast(error.message, true));
      return;
    }

    if (loginButton) {
      api(`/api/accounts/${account.id}/browser/open`, { method: "POST" })
        .then(() => loadLoginBrowser())
        .then(() => toast(`已打开 ${account.account_name} 的专用 Chrome；登录后看到头像，等待 10 秒再关闭`))
        .catch((error) => toast(error.message, true));
      return;
    }

    if (closeBrowserButton) {
      api("/api/browser/close", { method: "POST" })
        .then(() => loadLoginBrowser())
        .then(() => toast("登录窗口已关闭"))
        .catch((error) => toast(error.message, true));
      return;
    }

    if (!button) {
      const switchReason = accountSwitchBlockReason();
      if (switchReason) return toast(switchReason, true);
      state.accountId = account.id;
      renderAccounts();
      renderControls();
      await reloadAccountWorkspace();
      toast(`已切换到 ${account.account_name}`);
      return;
    }

    state.editingAccountId = account.id;
    state.accountEditorOpen = true;
    fillAccountForm(account);
    renderAccountEditor();
    elements["account-form"].scrollIntoView({ behavior: "smooth", block: "start" });
    elements["account-form"].account_name.focus();
  });

  elements["account-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = accountPayload();
      if (state.formMode === "create") {
        const account = await api("/api/accounts", { method: "POST", body: JSON.stringify(payload) });
        state.editingAccountId = "";
        state.accountEditorOpen = false;
        await loadAccounts(account.id);
        toast("账号已创建");
      } else {
        const editingId = state.editingAccountId;
        await api(`/api/accounts/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
        state.editingAccountId = "";
        state.accountEditorOpen = false;
        await loadAccounts(state.accountId || editingId);
        toast("账号已保存");
      }
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["account-form"].account_name.addEventListener("input", updateDerivedAccountPaths);
  elements["choose-account-root"].addEventListener("click", async () => {
    const button = elements["choose-account-root"];
    button.disabled = true;
    try {
      const result = await api("/api/folders/pick-account-root", { method: "POST" });
      if (!result.path) {
        toast("已取消选择文件夹");
        return;
      }
      state.accountRoot = result.path;
      elements["account-root-input"].value = result.path;
      updateDerivedAccountPaths();
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  elements["account-root-input"].addEventListener("click", () => elements["choose-account-root"].click());


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

  elements["refresh-songs"].addEventListener("click", async () => {
    try { await loadSongs(); toast("歌词列表已刷新"); } catch (error) { toast(error.message, true); }
  });
  elements["lyric-dir-input"].addEventListener("input", () => {
    renderLyricSource();
    renderControls();
  });
  elements["upload-dir-input"].addEventListener("input", () => {
    renderUploadSource();
    renderUploadRun();
  });
  elements["upload-ai-created"].addEventListener("change", () => {
    state.uploadAiCreated = elements["upload-ai-created"].value === "yes";
  });
  elements["upload-rejected-action"].addEventListener("change", () => {
    state.autoReplaceNoncompliant = elements["upload-rejected-action"].value === "replace";
    elements["pipeline-rejected-action"].value = elements["upload-rejected-action"].value;
  });
  elements["pipeline-rejected-action"].addEventListener("change", () => {
    state.autoReplaceNoncompliant = elements["pipeline-rejected-action"].value === "replace";
    elements["upload-rejected-action"].value = elements["pipeline-rejected-action"].value;
  });
  elements["apply-upload-dir"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    const current = state.accounts.find((item) => item.id === state.accountId);
    const outputDir = elements["upload-dir-input"].value.trim();
    if (!current || !outputDir) return toast("成品根目录不能为空", true);
    try {
      const updated = await api(`/api/accounts/${state.accountId}`, {
        method: "PUT",
        body: JSON.stringify({ ...current, output_dir: outputDir }),
      });
      state.accounts = state.accounts.map((item) => item.id === updated.id ? updated : item);
      if (!elements["account-form"].hidden && state.editingAccountId === updated.id) {
        elements["account-form"].output_dir.value = updated.output_dir;
      }
      await loadUploads();
      renderUploadRun();
      toast("成品目录已保存");
    } catch (error) {
      toast(error.message, true);
    }
  });
  elements["apply-lyric-dir"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    const current = state.accounts.find((item) => item.id === state.accountId);
    const lyricDir = elements["lyric-dir-input"].value.trim();
    if (!current || !lyricDir) return toast("歌词根目录不能为空", true);
    try {
      const updated = await api(`/api/accounts/${state.accountId}`, {
        method: "PUT",
        body: JSON.stringify({ ...current, lyric_dir: lyricDir }),
      });
      state.accounts = state.accounts.map((item) => item.id === updated.id ? updated : item);
      if (!elements["account-form"].hidden && state.editingAccountId === updated.id) {
        elements["account-form"].lyric_dir.value = updated.lyric_dir;
      }
      await loadSongs();
      await loadUploads();
      renderControls();
      toast("歌词目录已保存");
    } catch (error) {
      toast(error.message, true);
    }
  });
  elements["refresh-uploads"].addEventListener("click", async () => {
    try {
      await loadUploads();
      toast("上传批次已刷新");
    } catch (error) {
      toast(error.message, true);
    }
  });
  elements["upload-table"].addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-upload-file]");
    if (!checkbox || checkbox.disabled) return;
    const dailyLimit = Number(state.uploads?.daily_limit || 10);
    const dailyUsed = Number(
      state.uploads?.daily_used ?? (state.uploads?.uploaded_files || []).length,
    );
    const remaining = Number(
      state.uploads?.remaining_uploads ?? Math.max(0, dailyLimit - dailyUsed),
    );
    const limit = Math.min(Number(state.uploads?.batch_size || dailyLimit), remaining);
    if (checkbox.checked && state.selectedUploads.size >= limit) {
      checkbox.checked = false;
      toast(`一次最多发布 ${limit} 首`, true);
      return;
    }
    state.uploadSelectionTouched = true;
    if (checkbox.checked) state.selectedUploads.add(checkbox.dataset.uploadFile);
    else state.selectedUploads.delete(checkbox.dataset.uploadFile);
    renderUploads();
    renderUploadRun();
  });
  elements["select-all-uploads"].addEventListener("click", () => {
    const dailyLimit = Number(state.uploads?.daily_limit || 10);
    const dailyUsed = Number(
      state.uploads?.daily_used ?? (state.uploads?.uploaded_files || []).length,
    );
    const remaining = Number(
      state.uploads?.remaining_uploads ?? Math.max(0, dailyLimit - dailyUsed),
    );
    const limit = Math.min(Number(state.uploads?.batch_size || dailyLimit), remaining);
    state.selectedUploads = new Set((state.uploads?.files || []).slice(0, limit).map((file) => file.file_name));
    state.uploadSelectionTouched = true;
    renderUploads();
    renderUploadRun();
  });
  elements["clear-upload-selection"].addEventListener("click", () => {
    state.selectedUploads.clear();
    state.uploadSelectionTouched = true;
    renderUploads();
    renderUploadRun();
  });
  elements["start-upload"].addEventListener("click", async () => {
    if (!state.selectedTaskAccounts.size) return toast("请先勾选账号", true);
    try {
      const items = await buildUploadQueueItems();
      if (!items.length) return toast("所选账号都没有可上传曲目", true);
      state.multiQueue = await api("/api/multi-stage/upload/runs", {
        method: "POST",
        body: JSON.stringify({
          items,
          day: todayValue(),
          ai_created: state.uploadAiCreated,
          auto_replace_noncompliant: state.autoReplaceNoncompliant,
        }),
      });
      renderTaskAccounts();
      renderTaskStatus();
      renderControls();
      toast(items.length === 1 ? "上传任务已启动" : `已启动 ${items.length} 个账号的串联上传`);
    } catch (error) { toast(error.message, true); }
  });

  elements["retry-rejected-upload"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    const account = state.accounts.find((item) => item.id === state.accountId);
    const regenerateCount = state.uploads?.files?.length || 0;
    if (!regenerateCount) return toast("没有待发布的歌曲", true);
    try {
      state.uploadRun = await api(
        `/api/uploads/runs/retry-rejected?account_id=${encodeURIComponent(state.accountId)}&day=${encodeURIComponent(todayValue())}`,
        {
          method: "POST",
          body: JSON.stringify({
            ai_created: state.uploadAiCreated,
            model_name: account?.model_name || "自动",
            singer_name: singerNameForModel(account?.model_name || "自动", account?.singer_name),
          }),
        },
      );
      renderUploadRun();
      toast(`已开始再次生成发布 ${regenerateCount} 首`);
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["retry-uploads"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    const uploadedFiles = state.uploads?.uploaded_files || [];
    if (!uploadedFiles.length) return toast("没有已发布歌曲可重新提交", true);
    const fileNames = uploadedFiles.map((file) => file.file_name);
    const confirmed = confirm([
      `确定重新发布 ${fileNames.length} 首歌曲吗？`,
      "",
      "会先清除这些歌曲的本地“已发布”标记，然后重新提交整批专辑。",
      "如果平台其实已经发布成功，可能出现重复发布风险。",
    ].join("\n"));
    if (!confirmed) return;

    try {
      await api(`/api/accounts/${state.accountId}/uploads/reset?day=${encodeURIComponent(todayValue())}`, {
        method: "POST",
        body: JSON.stringify({ file_names: fileNames }),
      });
      state.selectedUploads = new Set(fileNames);
      state.uploadSelectionTouched = true;
      state.uploadRun = await api(
        `/api/uploads/runs?account_id=${encodeURIComponent(state.accountId)}&day=${encodeURIComponent(todayValue())}`,
        {
          method: "POST",
          body: JSON.stringify({
            file_names: fileNames,
            ai_created: state.uploadAiCreated,
            auto_replace_noncompliant: state.autoReplaceNoncompliant,
          }),
        },
      );
      renderUploadRun();
      toast(`已重新提交 ${fileNames.length} 首歌曲`);
    } catch (error) {
      toast(error.message, true);
      await loadUploads();
    }
  });
  elements["stop-upload"].addEventListener("click", async () => {
    if (multiStageRunning()) {
      try {
        state.multiQueue = await api("/api/multi-stage/runs/stop", { method: "POST" });
        renderTaskAccounts();
        renderTaskStatus();
        renderControls();
        toast("已请求停止多账号上传");
      } catch (error) { toast(error.message, true); }
      return;
    }
    try {
      state.uploadRun = await api("/api/uploads/runs/stop", { method: "POST" });
      renderUploadRun(); toast("已请求停止上传");
    } catch (error) { toast(error.message, true); }
  });

  elements["refresh-monitoring"].addEventListener("click", async () => {
    try {
      await loadMonitoringStatistics();
      await loadMonitoringCollection();
      toast("监控数据已刷新");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["monitoring-account-list"].addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-monitoring-account]");
    if (!checkbox || checkbox.disabled) return;
    if (checkbox.checked) state.monitoringSelectedAccountIds.add(checkbox.dataset.monitoringAccount);
    else state.monitoringSelectedAccountIds.delete(checkbox.dataset.monitoringAccount);
    renderMonitoring();
    void saveMonitoringSettings();
  });

  elements["monitoring-account-all"].addEventListener("click", () => {
    state.monitoringSelectedAccountIds = new Set(state.accounts.map((account) => account.id));
    renderMonitoring();
    void saveMonitoringSettings();
  });

  elements["monitoring-account-clear"].addEventListener("click", () => {
    state.monitoringSelectedAccountIds.clear();
    renderMonitoring();
    void saveMonitoringSettings();
  });

  elements["monitoring-view-list"].addEventListener("click", (event) => {
    const button = event.target.closest("[data-monitoring-view]");
    if (!button) return;
    state.monitoringViewAccountId = button.dataset.monitoringView;
    renderMonitoring();
  });

  elements["collect-monitoring"].addEventListener("click", async () => {
    if (!state.monitoringSelectedAccountIds.size) return toast("请先勾选采集账号", true);
    try {
      state.monitoringCollectionRequestSeq += 1;
      state.monitoringCollection = await api("/api/monitoring/collections", {
        method: "POST",
        body: JSON.stringify({ account_ids: [...state.monitoringSelectedAccountIds] }),
      });
      renderMonitoring();
      toast("已在后台开始采集监控数据");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["stop-monitoring"].addEventListener("click", async () => {
    try {
      state.monitoringCollection = await api("/api/monitoring/collections/stop", { method: "POST" });
      renderMonitoring();
      toast("已请求停止监控采集");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["pipeline-queue-list"].addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-queue-account]");
    if (!checkbox || checkbox.disabled) return;
    if (checkbox.checked) state.selectedPipelineQueueAccounts.add(checkbox.dataset.queueAccount);
    else state.selectedPipelineQueueAccounts.delete(checkbox.dataset.queueAccount);
    state.selectedTaskAccounts = new Set(state.selectedPipelineQueueAccounts);
    renderTaskAccounts();
    renderPipelinePanel();
  });

  elements["pipeline-queue-table"].addEventListener("click", (event) => {
    const button = event.target.closest("[data-pipeline-detail]");
    if (!button || button.disabled) return;
    state.selectedPipelineDetailAccountId = button.dataset.pipelineDetail;
    state.pipelineDetailPinned = true;
    renderPipelinePanel();
  });

  elements["pipeline-queue-list"].addEventListener("click", (event) => {
    const up = event.target.closest("[data-queue-move-up]");
    const down = event.target.closest("[data-queue-move-down]");
    const accountId = up?.dataset.queueMoveUp || down?.dataset.queueMoveDown;
    if (!accountId) return;
    const index = state.pipelineQueueOrder.indexOf(accountId);
    const target = up ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= state.pipelineQueueOrder.length) return;
    [state.pipelineQueueOrder[index], state.pipelineQueueOrder[target]] = [
      state.pipelineQueueOrder[target],
      state.pipelineQueueOrder[index],
    ];
    state.pipelineQueueOptions.sort((
      first,
      second,
    ) => state.pipelineQueueOrder.indexOf(first.account_id) - state.pipelineQueueOrder.indexOf(second.account_id));
    renderPipelinePanel();
  });

  elements["pipeline-start"].addEventListener("click", async () => {
    const rows = [...elements["pipeline-queue-list"].querySelectorAll(".pipeline-queue-option")]
      .filter((row) => row.querySelector("input[data-queue-account]")?.checked);
    if (!rows.length) return toast("请至少勾选一个账号", true);
    const items = rows.map((row) => ({
      account_id: row.dataset.accountId,
      template_id: row.querySelector("select").value,
    }));
    if (items.some((item) => !item.template_id)) return toast("所选账号必须有作词模板", true);
    try {
      state.pipelineQueue = await api("/api/pipeline/queue/runs", {
        method: "POST",
        body: JSON.stringify({
          items,
          day: todayValue(),
          pause_before_upload: elements["pipeline-pause"].checked,
          ai_created: elements["pipeline-ai-created"].value === "yes",
          auto_replace_noncompliant: state.autoReplaceNoncompliant,
          model_name: state.generationModel || elements["pipeline-model"].value,
          singer_name: elements["pipeline-singer"].value,
        }),
      });
      renderPipelinePanel();
      renderControls();
      toast(items.length === 1 ? "单账号流水线已启动" : `已启动 ${items.length} 个账号的串联队列`);
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["pipeline-resume"].addEventListener("click", async () => {
    try {
      state.pipelineQueue = await api("/api/pipeline/queue/runs/resume", { method: "POST" });
      renderPipelinePanel();
      renderControls();
      toast("已继续队列上传流程");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["pipeline-stop"].addEventListener("click", async () => {
    try {
      state.pipelineQueue = await api("/api/pipeline/queue/runs/stop", { method: "POST" });
      renderPipelinePanel();
      renderControls();
      toast("多账号队列已停止");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["pipeline-refresh"].addEventListener("click", async () => {
    try {
      await loadPipelineQueue();
      await loadPipelineRun();
      toast("队列状态已刷新");
    } catch (error) {
      toast(error.message, true);
    }
  });

function fillLyricTemplateForm(template = null) {
    state.lyricTemplateEditorOpen = true;
    state.editingLyricTemplateId = template?.id || "";
    state.lyricTemplateAccountLocked = Boolean(template);
    state.selectedTemplateThemes = template ? [...template.themes] : [];
    elements["template-account-select"].value = template?.account_id || state.accountId || "";
    elements["template-name"].value = template?.name || "";
    elements["template-lyric-tone"].value = template?.lyric_tone || "";
    elements["template-song-style"].value = template?.song_style || "";
    elements["template-generation-count"].value = template?.generation_count || 1;
    elements["custom-theme"].value = "";
    renderTemplateOutputLocation();
    renderLyricTemplateEditor();
    elements["template-name"].focus();
  }

  elements["new-lyric-template"].addEventListener("click", () => {
    if (!state.accounts.length) return toast("请先创建妙响账号", true);
    fillLyricTemplateForm();
  });

  elements["multi-lyrics-start"].addEventListener("click", async () => {
    if (!state.selectedTaskAccounts.size) return toast("请先勾选账号", true);
    try {
      const items = await buildLyricQueueItems();
      if (!items.length) return toast("所选账号都没有作词模板", true);
      state.multiQueue = await api("/api/multi-stage/lyrics/runs", {
        method: "POST",
        body: JSON.stringify({ items, day: todayValue() }),
      });
      syncLyricQueueSnapshot(state.multiQueue);
      renderTaskAccounts();
      renderTaskStatus();
      renderControls();
      toast(items.length === 1 ? "AI 作词已启动" : `已并联启动 ${items.length} 个账号的 AI 作词`);
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["lyric-template-cards"].addEventListener("click", async (event) => {
    const generateButton = event.target.closest("[data-generate-template]");
    const editButton = event.target.closest("[data-edit-lyric-template]");
    const deleteButton = event.target.closest("[data-delete-lyric-template]");
    const useButton = event.target.closest("[data-use-lyric-template]");
    const button = generateButton || useButton || editButton || deleteButton;
    if (!button) return;
    const template = state.lyricTemplates.find(
      (item) => item.id === (
        generateButton?.dataset.generateTemplate
        || useButton?.dataset.useLyricTemplate
        || editButton?.dataset.editLyricTemplate
        || deleteButton?.dataset.deleteLyricTemplate
      ),
    );
    if (!template) return;

    if (generateButton) {
      state.selectedLyricTemplateId = template.id;
      state.accountId = template.account_id;
      renderAccounts();
      renderControls();
      state.lyricGenerating = true;
      state.lyricProgress = {
        stage: "connecting",
        message: "正在连接 AI API",
        elapsed_seconds: 0,
        expected_count: template.generation_count,
        content_chars: 0,
        reasoning_available: false,
        reasoning_excerpt: "",
        song_names: [],
      };
      state.lyricProgressStartedAt = Date.now();
      clearInterval(state.lyricProgressTimer);
      state.lyricProgressTimer = setInterval(() => {
        if (state.lyricGenerating) renderLyricProgress();
      }, 1000);
      renderLyricControls();
      renderLyricProgress();
      try {
        const result = await generateLyricsStream(template.account_id, template.id);
        state.lyricResults = result.songs;
        state.lyricProgress = {
          ...state.lyricProgress,
          stage: "completed",
          message: "生成完成",
          song_names: result.songs.map((song) => song.song_name),
          expected_count: result.songs.length,
        };
        renderLyricResults();
        toast(`已生成 ${result.songs.length} 首歌词草稿`);
      } catch (error) {
        state.lyricProgress = {
          ...(state.lyricProgress || {}),
          stage: "failed",
          message: error.message,
        };
        toast(error.message, true);
      } finally {
        state.lyricGenerating = false;
        clearInterval(state.lyricProgressTimer);
        state.lyricProgressTimer = null;
        renderLyricProgress();
        renderLyricControls();
      }
      return;
    }

    if (useButton) {
      state.selectedLyricTemplateId = template.id;
      renderLyricTemplateCards();
      renderLyricWorkspace();
      toast(`已选择模板：${template.name}`);
      return;
    }

    if (deleteButton) {
      if (!confirm(`确定删除模板“${template.name}”？`)) return;
      try {
        await api(`/api/accounts/${template.account_id}/lyric/templates/${template.id}`, { method: "DELETE" });
        await loadLyricTemplates();
        await loadPipelineQueueOptions();
        toast("模板已删除");
      } catch (error) {
        toast(error.message, true);
      }
      return;
    }

    state.accountId = template.account_id;
    await loadLyricTemplates().catch(() => {});
    fillLyricTemplateForm(template);
  });

  elements["template-theme-options"].addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-theme-option]");
    if (!checkbox) return;
    const themes = new Set(state.selectedTemplateThemes);
    if (checkbox.checked) themes.add(checkbox.value);
    else themes.delete(checkbox.value);
    state.selectedTemplateThemes = [...themes];
  });

  elements["template-account-select"].addEventListener("change", renderTemplateOutputLocation);

  elements["add-custom-theme"].addEventListener("click", () => {
    const theme = elements["custom-theme"].value.trim();
    if (!theme) return toast("请输入自定义主题", true);
    if (!state.selectedTemplateThemes.includes(theme)) state.selectedTemplateThemes.push(theme);
    elements["custom-theme"].value = "";
    renderThemeOptions();
  });

  elements["cancel-lyric-template"].addEventListener("click", () => {
    state.lyricTemplateEditorOpen = false;
    state.editingLyricTemplateId = "";
    state.lyricTemplateAccountLocked = false;
    state.selectedTemplateThemes = [];
    renderLyricTemplateEditor();
  });

  elements["lyric-template-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    const accountId = elements["template-account-select"].value;
    const selectedThemes = [...elements["template-theme-options"].querySelectorAll("input:checked")]
      .map((checkbox) => checkbox.value)
      .filter(Boolean);
    const payload = {
      name: elements["template-name"].value.trim(),
      lyric_tone: elements["template-lyric-tone"].value.trim(),
      song_style: elements["template-song-style"].value.trim(),
      themes: selectedThemes,
      generation_count: Math.min(10, Math.max(1, Number(elements["template-generation-count"].value || 1))),
    };
    if (!accountId) return toast("请选择模板绑定的账号", true);
    if (!payload.name) return toast("请填写模板名称", true);
    if (!payload.themes.length) {
      return toast("主题至少选择一个；自定义主题需点击“添加”后再保存", true);
    }
    if (!payload.generation_count) {
      return toast("请填写生成数量", true);
    }
    try {
      if (state.editingLyricTemplateId) {
        const updated = await api(`/api/accounts/${accountId}/lyric/templates/${state.editingLyricTemplateId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        state.selectedLyricTemplateId = updated.id;
      } else {
        const created = await api(`/api/accounts/${accountId}/lyric/templates`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        state.selectedLyricTemplateId = created.id;
      }
      state.lyricTemplateEditorOpen = false;
      state.editingLyricTemplateId = "";
      state.lyricTemplateAccountLocked = false;
      state.accountId = accountId;
      renderAccounts();
      await loadSongs();
      await loadLyricTemplates();
      await loadPipelineQueueOptions();
      toast("模板已保存");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["lyric-results"].addEventListener("input", (event) => {
    const target = event.target.closest("[data-lyric-field]");
    if (!target) return;
    const index = Number(target.dataset.lyricIndex);
    const field = target.dataset.lyricField;
    if (!state.lyricResults[index]) return;
    state.lyricResults[index][field] = target.value;
  });

  elements["lyric-results"].addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-lyric]");
    if (!button) return;
    state.lyricResults.splice(Number(button.dataset.removeLyric), 1);
    renderLyricResults();
    renderLyricControls();
  });

  elements["save-lyric-prompt"].addEventListener("click", async () => {
    const prompt = elements["lyric-system-prompt"].value.trim();
    if (prompt.length < 100) return toast("通用规则至少 100 个字符", true);
    state.lyricPromptSaving = true;
    renderLyricPromptState();
    try {
      state.settings = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ ai_system_prompt: prompt }),
      });
      state.lyricSystemPrompt = state.settings.ai_system_prompt;
      elements["lyric-system-prompt"].value = state.lyricSystemPrompt;
      state.lyricPromptDirty = false;
      toast("通用规则已保存");
    } catch (error) {
      toast(error.message, true);
    } finally {
      state.lyricPromptSaving = false;
      renderLyricPromptState();
      elements["lyric-prompt-details"].open = state.lyricPromptDirty;
    }
  });

  elements["lyric-system-prompt"].addEventListener("input", () => {
    state.lyricPromptDirty = elements["lyric-system-prompt"].value !== state.lyricSystemPrompt;
    renderLyricPromptState();
  });


  elements["save-lyrics"].addEventListener("click", async () => {
    if (!state.accountId || !state.lyricResults.length) return;
    try {
      const result = await api(`/api/accounts/${state.accountId}/lyrics/save`, {
        method: "POST",
        body: JSON.stringify({
          day: todayValue(),
          songs: state.lyricResults,
        }),
      });
      state.lyricResults = [];
      renderLyricResults();
      await loadSongs();
      state.stage = "generation";
      state.view = "task";
      renderView();
      toast(`已保存 ${result.saved.length} 首歌词`);
    } catch (error) {
      toast(error.message, true);
    }
  });
  elements["select-all"].addEventListener("click", () => {
    state.selected = new Set(state.songs.filter((song) => song.valid).map((song) => song.file_name));
    renderSongs();
  });
  elements["select-failed"].addEventListener("click", () => {
    state.selected = new Set(
      state.songs
        .filter((song) => !song.valid || isFailureStatus(songState(song)))
        .map((song) => song.file_name),
    );
    renderSongs();
  });
  elements["repair-run"].addEventListener("click", async () => {
    if (!state.selectedTaskAccounts.size) return toast("请先勾选账号", true);
    if (!selectedAccountsHaveRepairSongs()) {
      return toast("当前没有可自动修复的异常歌曲", true);
    }
    try {
      state.multiQueue = await api("/api/multi-stage/repair/runs", {
        method: "POST",
        body: JSON.stringify({
          items: selectedTaskAccounts().map((account) => ({ account_id: account.id })),
          day: todayValue(),
        }),
      });
      renderTaskAccounts();
      renderTaskStatus();
      renderControls();
      toast(`已开始修复 ${state.multiQueue.items.length} 个账号的异常`);
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["generation-model"].addEventListener("change", () => {
    saveGenerationModel(elements["generation-model"].value);
  });
  elements["generation-singer"].addEventListener("change", () => {
    saveGenerationSinger(elements["generation-singer"].value);
  });
  elements["pipeline-model"].addEventListener("change", () => {
    saveGenerationModel(elements["pipeline-model"].value);
    renderPipelinePanel();
  });
  elements["pipeline-singer"].addEventListener("change", () => {
    saveGenerationSinger(elements["pipeline-singer"].value);
  });

  elements["start-run"].addEventListener("click", async () => {
    if (!state.selectedTaskAccounts.size) return toast("请先勾选账号", true);
    try {
      const selectedAccounts = selectedTaskAccounts();
      const selectedIds = new Set(selectedAccounts.map((account) => account.id));
      const { items, skipped } = await buildGenerationQueueItems(selectedAccounts);
      if (!items.length) return toast("所选账号都没有可生成歌词", true);
      const currentSelectedIds = new Set(state.selectedTaskAccounts);
      if (
        selectedIds.size !== currentSelectedIds.size
        || [...selectedIds].some((accountId) => !currentSelectedIds.has(accountId))
      ) {
        return toast("账号选择状态发生变化，请重新确认后再开始生成", true);
      }
      if (items.length + skipped.length !== selectedAccounts.length) {
        return toast("账号选择状态发生变化，请重新确认后再开始生成", true);
      }
      const skippedIds = new Set(
        skipped.map((account) => account.id),
      );
      const itemRequests = items.map((item) => {
        const account = state.accounts.find((entry) => entry.id === item.account_id);
        return {
          ...item,
          model_name: account?.model_name || "自动",
          singer_name: singerNameForModel(account?.model_name || "自动", account?.singer_name),
        };
      });
      state.multiQueue = await api("/api/multi-stage/generation/runs", {
        method: "POST",
        body: JSON.stringify({
          items: itemRequests,
          day: todayValue(),
          fresh_run: elements["fresh-run"].checked,
          model_name: "自动",
          singer_name: "",
        }),
      });
      const queuedIds = new Set(state.multiQueue.items.map((item) => item.account_id));
      const missingAccounts = selectedAccounts.filter((account) => !skippedIds.has(account.id) && !queuedIds.has(account.id));
      if (missingAccounts.length) {
        toast(`队列缺少账号：${missingAccounts.map((account) => account.account_name).join("、")}`, true);
      } else if (skipped.length) {
        toast(`已跳过 ${skipped.map((account) => account.name).join("、")}：今天没有可处理歌词`, true);
      } else {
        const queueNames = state.multiQueue.items.map((item) => item.account_name).join(" → ");
        toast(items.length === 1
          ? `生成任务已启动：${queueNames}`
          : `已启动 ${items.length} 个账号，最多 2 个同时执行：${queueNames}`);
      }
      renderTaskAccounts();
      renderTaskStatus();
      renderControls();
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["pause-run"].addEventListener("click", () => runControl("pause"));
  elements["resume-run"].addEventListener("click", () => runControl("resume"));
  elements["stop-run"].addEventListener("click", () => runControl("stop"));

  elements["settings-form"].addEventListener("submit", (event) => event.preventDefault());
  elements["save-settings"].addEventListener("click", async () => {
    const runtimeActive = state.settingsTab === "runtime";
    try {
      let payload = {};
      if (runtimeActive) {
        const form = elements["settings-form"];
        for (const input of form.elements) {
          if (!input.name) continue;
          payload[input.name] = Number(input.value);
        }
      } else {
        const form = elements["ai-settings-form"];
        const provider = {
          id: form.ai_provider_id.value.trim() || `local-${Date.now().toString(36)}`,
          name: form.ai_provider_name.value.trim(),
          api_base_url: form.ai_api_base_url.value.trim(),
          api_key: form.ai_api_key.value.trim(),
          model: form.ai_model.value.trim(),
          max_retries: Math.min(5, Math.max(0, Number(form.ai_max_retries.value || 2))),
        };
        if (!provider.name) return toast("请填写接口名称", true);
        if (!provider.api_base_url || !provider.model) return toast("请填写 API 地址和模型", true);
        const configs = aiApiConfigs().filter((item) => item.id !== provider.id);
        configs.push(provider);
        payload = {
          ai_api_configs: configs,
          active_ai_api_config_id: provider.id,
        };
      }
      state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      if (!runtimeActive) state.aiConfigEditorOpen = false;
      state.aiApiChecks = {};
      await loadSettings();
      toast(runtimeActive ? "运行参数已保存" : "AI API 配置已保存");
    } catch (error) {
      toast(error.message, true);
    }
  });

  elements["settings-tab-runtime"].addEventListener("click", () => {
    state.settingsTab = "runtime";
    renderSettingsTabs();
  });
  elements["settings-tab-ai"].addEventListener("click", () => {
    state.settingsTab = "ai";
    renderSettingsTabs();
  });
  elements["settings-tab-prompt"].addEventListener("click", () => {
    state.settingsTab = "prompt";
    renderSettingsTabs();
    renderLyricPromptState();
  });

  elements["ai-provider-select"].addEventListener("change", async () => {
    const config = aiApiConfigs().find((item) => item.id === elements["ai-provider-select"].value);
    if (!config || config.id === state.settings?.active_ai_api_config_id) return;
    try {
      state.settings = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ active_ai_api_config_id: config.id }),
      });
      renderSettingsTabs();
      renderControls();
      toast(`AI 作词已切换到 ${config.name}`);
    } catch (error) {
      toast(error.message, true);
      syncAiProviderSelect();
    }
  });

  elements["ai-config-cards"].addEventListener("click", async (event) => {
    const button = event.target.closest(
      "[data-add-ai-config], [data-test-ai-config], [data-edit-ai-config], [data-use-ai-config], [data-delete-ai-config]"
    );
    if (!button || button.disabled) return;
    if (button.dataset.addAiConfig) {
      state.aiConfigEditorOpen = true;
      state.editingAIProviderId = "";
      fillAiApiForm(null);
      renderSettingsTabs();
      elements["ai-settings-form"].ai_provider_name.focus();
      return;
    }
    if (button.dataset.testAiConfig) {
      const config = aiApiConfigs().find((item) => item.id === button.dataset.testAiConfig);
      if (!config) return;
      if (Object.values(state.aiApiChecks).some((item) => item.status === "checking")) {
        return toast("已有接口正在检测，请稍候", true);
      }
      const startedAt = Date.now();
      state.aiApiChecks = {
        ...state.aiApiChecks,
        [config.id]: { status: "checking" },
      };
      renderAiApiConfigCards();
      try {
        const result = await api("/api/settings/ai/test", {
          method: "POST",
          body: JSON.stringify({
            ai_api_base_url: config.api_base_url,
            ai_api_key: config.api_key,
            ai_model: config.model,
          }),
        });
        state.aiApiChecks[config.id] = {
          status: "success",
          model_count: result.model_count,
          elapsed_ms: Date.now() - startedAt,
        };
        toast(`${config.name} 连接成功`);
      } catch (error) {
        state.aiApiChecks[config.id] = {
          status: "failed",
          error: error.message,
          elapsed_ms: Date.now() - startedAt,
        };
        toast(`${config.name} 检测失败：${error.message}`, true);
      } finally {
        renderAiApiConfigCards();
      }
      return;
    }
    if (button.dataset.editAiConfig) {
      const config = aiApiConfigs().find((item) => item.id === button.dataset.editAiConfig);
      if (!config) return;
      state.aiConfigEditorOpen = true;
      state.editingAIProviderId = config.id;
      fillAiApiForm(config);
      renderSettingsTabs();
      elements["ai-settings-form"].ai_provider_name.focus();
      return;
    }
    if (button.dataset.useAiConfig) {
      const config = aiApiConfigs().find((item) => item.id === button.dataset.useAiConfig);
      if (!config) return;
      try {
        state.settings = await api("/api/settings", {
          method: "PUT",
          body: JSON.stringify({ active_ai_api_config_id: config.id }),
        });
        renderSettingsTabs();
        renderControls();
        toast(`已切换到 ${config.name}`);
      } catch (error) {
        toast(error.message, true);
      }
      return;
    }
    if (button.dataset.deleteAiConfig) {
      const config = aiApiConfigs().find((item) => item.id === button.dataset.deleteAiConfig);
      if (!config || !confirm(`确定删除 AI 接口“${config.name}”？`)) return;
      const configs = aiApiConfigs().filter((item) => item.id !== config.id);
      const payload = {
        ai_api_configs: configs,
        active_ai_api_config_id: configs[0]?.id || "",
      };
      if (!configs.length) {
        Object.assign(payload, {
          ai_api_base_url: "",
          ai_api_key: "",
          ai_model: "",
          ai_max_retries: 2,
        });
      }
      try {
        state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
        if (state.editingAIProviderId === config.id) {
          state.aiConfigEditorOpen = false;
          state.editingAIProviderId = "";
        }
        await loadSettings();
        renderControls();
        toast("AI 接口已删除");
      } catch (error) {
        toast(error.message, true);
      }
    }
  });

  elements["ai-config-cancel"].addEventListener("click", () => {
    if (!aiApiConfigs().length) return;
    state.aiConfigEditorOpen = false;
    state.editingAIProviderId = "";
    renderSettingsTabs();
  });

  elements["test-ai-settings"].addEventListener("click", async () => {
    const form = elements["ai-settings-form"];
    const payload = {
      ai_api_base_url: form.ai_api_base_url.value.trim(),
      ai_api_key: form.ai_api_key.value.trim(),
      ai_model: form.ai_model.value.trim(),
    };
    const name = form.ai_provider_name.value.trim();
    if (!name || !payload.ai_api_base_url || !payload.ai_model) {
      return toast("请先填写接口名称、API 地址和模型", true);
    }
    elements["test-ai-settings"].disabled = true;
    elements["test-ai-settings"].textContent = "测试中";
    try {
      const result = await api("/api/settings/ai/test", { method: "POST", body: JSON.stringify(payload) });
      toast(`连接成功：${result.model}，可用模型 ${result.model_count} 个`);
    } catch (error) {
      toast(error.message, true);
    } finally {
      elements["test-ai-settings"].disabled = false;
      elements["test-ai-settings"].textContent = "测试连接";
    }
  });

  elements["copy-logs"].addEventListener("click", async () => {
    const text = state.logs.map((entry) => `${formatTime(entry.timestamp)} ${entry.step} ${entry.message}`).join("\n");
    await navigator.clipboard.writeText(text);
    toast("日志已复制");
  });
  elements["open-logs"].addEventListener("click", () => openFolder("logs"));
  elements["open-screenshots"].addEventListener("click", () => openFolder("screenshots"));
}

async function openFolder(kind) {
  try {
    await api("/api/folders/open", { method: "POST", body: JSON.stringify({ kind }) });
    toast("已打开目录");
  } catch (error) {
    toast(error.message, true);
  }
}
