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
  autoReplaceNoncompliant: true,
  pipelineRun: null,
  pipelineSyncedSignature: "",
  pipelineQueue: null,
  pipelineQueueOptions: [],
  pipelineQueueOrder: [],
  selectedPipelineQueueAccounts: new Set(),
  selectedPipelineDetailAccountId: "",
  pipelineDetailPinned: false,
  current: null,
  runStatus: "",
  notifiedRunId: "",
  settings: null,
  logs: [],
  socket: null,
  socketTimer: null,
  pollTimer: null,
  formMode: "edit",
  view: "task",
  stage: "generation",
  generationModel: "自动",
  generationSinger: "",
  settingsTab: "runtime",
  accountMenuOpen: false,
  accountReloadId: 0,
  accountRoot: "",
  aiConfigEditorOpen: false,
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
};

const THEME_OPTIONS = ["爱情", "友情", "校园", "都市", "治愈", "励志", "古风", "家庭", "旅行", "孤独"];
const DEFAULT_CREATE_URL = "https://music.douyin.com/studio/create";
const GENERATION_MODEL_STORAGE_KEY = "aimusic.generationModel";
const GENERATION_SINGER_STORAGE_KEY = "aimusic.generationSinger";

const elements = {};

for (const id of [
  "service-status", "socket-status", "task-status", "account-select", "account-form",
  "account-new", "account-cancel", "account-copy", "account-cards", "account-switcher",
  "account-menu-button", "account-menu-value", "account-menu",
  "account-root-field", "account-root-input", "choose-account-root", "account-derived-paths",
  "derived-lyric-path", "derived-output-path", "derived-download-path", "derived-chrome-path",
  "chrome-profile-field", "lyric-dir-field", "output-dir-field", "download-dir-field",
  "queue-caption", "select-all",
  "generation-model", "generation-singer",
  "select-failed", "refresh-songs", "start-run", "pause-run", "resume-run", "stop-run",
  "fresh-run", "metric-pending", "metric-success", "metric-skip", "metric-fail",
  "metric-step", "song-table", "queue-empty", "settings-form", "save-settings",
  "ai-settings-form", "settings-subnav", "settings-tab-runtime", "settings-tab-ai", "test-ai-settings",
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
  "lyric-system-prompt", "save-lyric-prompt", "lyric-results", "lyric-empty", "save-lyrics",
  "lyric-prompt-details",
  "lyric-progress-panel", "lyric-progress-message", "lyric-progress-elapsed", "lyric-progress-chars",
  "lyric-progress-count", "lyric-progress-names", "lyric-progress-reasoning",
  "lyric-result-caption",
  "lyric-template-caption", "lyric-template-cards", "lyric-template-form", "new-lyric-template",
  "template-account-select", "template-name", "template-lyric-tone", "template-song-style",
  "template-generation-count", "template-output-location",
  "template-theme-options", "custom-theme", "add-custom-theme", "save-lyric-template",
  "cancel-lyric-template",
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
    const activeView = state.view === "lyrics" ? "task" : state.view;
    item.classList.toggle("is-active", item.dataset.view === activeView);
  });
  renderStages();
  renderSettingsTabs();
}

function renderStages() {
  document.body.dataset.stage = state.stage;
  document.querySelectorAll(".stage").forEach((item) => {
    const active = item.dataset.stage === state.stage;
    item.classList.toggle("is-active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
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
    verification_failed: "标题校验失败",
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
  renderAccountMenu();
  renderAccountCards();
  renderAccountEditor();
}

function accountSwitchBlockReason() {
  if (isRunning()) return "生成任务运行中不能切换账号";
  if (uploadRunning()) {
    return ["waiting_verification_code", "waiting_external_verification_code"]
      .includes(state.uploadRun?.step)
      ? "上传任务正在等待手机验证码；提交验证码或停止上传后才能切换账号"
      : "上传任务运行中不能切换账号";
  }
  if (pipelineWorkflowBusy()) return "完整流水线运行中不能切换账号";
  return "";
}

function accountMenuDisabled() {
  return Boolean(accountSwitchBlockReason());
}

function renderAccountMenu() {
  const selected = state.accounts.find((account) => account.id === state.accountId);
  elements["account-menu-value"].textContent = selected
    ? selected.account_name
    : state.accounts.length
      ? "选择账号"
      : "暂无账号";
  elements["account-menu-button"].disabled = accountMenuDisabled();
  elements["account-menu-button"].setAttribute("aria-expanded", state.accountMenuOpen ? "true" : "false");
  elements["account-menu-button"].dataset.tip = accountSwitchBlockReason() || "切换当前妙响账号";
  elements["account-switcher"].classList.toggle("is-open", state.accountMenuOpen);

  const menu = elements["account-menu"];
  menu.innerHTML = "";
  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "account-menu-empty";
    empty.textContent = "暂无可切换账号";
    menu.append(empty);
    return;
  }

  for (const account of state.accounts) {
    const option = document.createElement("button");
    option.type = "button";
    option.className = `account-menu-option${account.id === state.accountId ? " is-selected" : ""}`;
    option.dataset.accountMenuId = account.id;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", account.id === state.accountId ? "true" : "false");
    const name = document.createElement("span");
    name.className = "account-menu-name";
    name.textContent = account.account_name;
    const port = document.createElement("small");
    port.className = "account-menu-port";
    port.textContent = `端口 ${account.chrome_debug_port}`;
    option.append(name, port);
    menu.append(option);
  }
}

function setAccountMenuOpen(open) {
  if (open && accountMenuDisabled()) {
    toast(accountSwitchBlockReason(), true);
    return;
  }
  state.accountMenuOpen = open;
  renderAccountMenu();
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
  const visible = elements["generation-model"].value === "Sway v5.5";
  const disabled = Boolean(locked);
  for (const select of generationModelSelects()) select.disabled = disabled;
  for (const select of generationSingerSelects()) {
    const field = select.closest(".singer-field");
    if (field) field.hidden = !visible;
    select.disabled = disabled || !visible;
  }
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

function renderSettingsTabs() {
  const runtimeActive = state.settingsTab === "runtime";
  const aiConfigured = Boolean(state.settings?.ai_api_base_url && state.settings?.ai_model);
  const showAiForm = !runtimeActive && (!aiConfigured || state.aiConfigEditorOpen);
  const showAiCard = !runtimeActive && aiConfigured && !state.aiConfigEditorOpen;
  elements["settings-subnav"].hidden = state.view !== "settings";
  elements["settings-tab-runtime"].classList.toggle("is-active", runtimeActive);
  elements["settings-tab-ai"].classList.toggle("is-active", !runtimeActive);
  elements["settings-form"].hidden = !runtimeActive;
  elements["ai-config-cards"].hidden = !showAiCard;
  elements["ai-settings-form"].hidden = !showAiForm;
  elements["ai-config-cancel"].hidden = !state.aiConfigEditorOpen;
  elements["save-settings"].hidden = !runtimeActive && !showAiForm;
  elements["save-settings"].textContent = runtimeActive ? "保存参数" : "保存 AI 配置";
  if (showAiCard) renderAiConfigCard();
}

function maskApiKey(key) {
  if (!key) return "未填写";
  if (key.length <= 8) return "****";
  return `${key.slice(0, 4)}****${key.slice(-4)}`;
}

function renderAiConfigCard() {
  const container = elements["ai-config-cards"];
  const settings = state.settings;
  if (!settings?.ai_api_base_url || !settings?.ai_model) {
    container.innerHTML = "";
    return;
  }

  const card = document.createElement("article");
  card.className = "settings-card is-ai";
  const main = document.createElement("div");
  main.className = "settings-card-main";
  const title = document.createElement("h3");
  title.textContent = "AI 作词接口";
  const badge = document.createElement("span");
  badge.className = "state state-success";
  badge.textContent = "已配置";
  main.append(title, badge);

  const details = document.createElement("dl");
  details.className = "settings-card-details";
  for (const [label, value] of [
    ["API Base URL", settings.ai_api_base_url],
    ["模型", settings.ai_model],
    ["API Key", maskApiKey(settings.ai_api_key)],
    ["重试次数", String(settings.ai_max_retries)],
  ]) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    description.title = value;
    details.append(term, description);
  }

  const actions = document.createElement("div");
  actions.className = "settings-card-actions";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "button";
  edit.textContent = "修改配置";
  edit.dataset.editAiConfig = "true";
  edit.disabled = isRunning() || uploadRunning();
  actions.append(edit);

  card.append(main, details, actions);
  container.innerHTML = "";
  container.append(card);
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
  const disabled = !state.accountId || !state.selectedLyricTemplateId || state.lyricGenerating || isRunning() || uploadRunning() || pipelineWorkflowBusy();
  document.querySelectorAll("[data-generate-template]").forEach((button) => {
    button.disabled = disabled || button.dataset.generateTemplate !== state.selectedLyricTemplateId;
    button.textContent = state.lyricGenerating ? "生成中" : "生成歌词";
  });
  elements["save-lyrics"].disabled = !state.accountId || !state.lyricResults.length || state.lyricGenerating || isRunning() || uploadRunning() || pipelineWorkflowBusy();
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
    if (template.id === state.selectedLyricTemplateId) {
      const generate = document.createElement("button");
      generate.type = "button";
      generate.className = "button primary";
      generate.textContent = "生成歌词";
      generate.dataset.generateTemplate = template.id;
      generate.disabled = state.lyricGenerating || isRunning() || uploadRunning();
      actions.append(generate);
    }
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
    song_interval_seconds: 5,
  };
  state.accountRoot = account ? inferAccountRoot(account) : "";
  form.reset();
  for (const [key, value] of Object.entries(values)) {
    if (form.elements[key]) form.elements[key].value = value;
  }
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
  const limit = state.uploads?.batch_size || 10;
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
    ? `${state.uploads.day} · 待发布 ${selectedCount}/${files.length} · 已发布 ${uploadedFiles.length}`
    : "等待成品下载完成";

  for (const file of allFiles) {
    const row = document.createElement("div");
    row.className = "upload-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedUploads.has(file.file_name);
    checkbox.disabled = file.uploaded || uploadRunning() || isRunning();
    checkbox.dataset.uploadFile = file.file_name;
    const name = document.createElement("span");
    name.textContent = file.file_name;
    name.title = file.path;
    const size = document.createElement("span");
    size.textContent = formatSize(file.size);
    const status = document.createElement("span");
    status.innerHTML = file.uploaded
      ? '<span class="state state-success">已发布</span>'
      : '<span class="state state-waiting">待发布</span>';
    row.append(checkbox, name, size, status);
    elements["upload-table"].append(row);
  }
  renderUploadSource();
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

function renderUploadRun() {
  const run = state.uploadRun;
  const account = state.accounts.find((item) => item.id === state.accountId);
  const uploadedFiles = state.uploads?.uploaded_files || [];
  const uploadDirDirty = Boolean(account) && elements["upload-dir-input"].value.trim() !== account.output_dir;
  const pipelineBusy = pipelineWorkflowBusy();
  elements["start-upload"].disabled = !state.accountId || !state.uploads?.files?.length || !state.selectedUploads.size || uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
  elements["select-all-uploads"].disabled = isRunning() || uploadRunning() || pipelineBusy;
  elements["clear-upload-selection"].disabled = isRunning() || uploadRunning() || pipelineBusy;
  elements["refresh-uploads"].disabled = uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
  elements["retry-uploads"].disabled = !uploadedFiles.length || uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
  elements["retry-rejected-upload"].disabled = !state.uploads?.files?.length || uploadDirDirty || isRunning() || uploadRunning() || pipelineBusy;
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
    };
    elements["upload-caption"].textContent = labels[run.step] || run.step;
  } else if (run?.status === "completed") {
    elements["upload-caption"].textContent = run.replaced_titles?.length
      ? `发布完成；已自动替换 ${run.replaced_titles.length} 首`
      : "发布完成";
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
  if (!song.valid) return "解析失败";
  if (state.current && state.current.account_id === state.accountId) {
    const match = state.current.songs.find((item) => item.file_name === song.file_name);
    if (match) return match.status;
  }
  return song.status || "pending";
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
  const running = state.songs.filter((song) => songState(song) === "pending" || songState(song) === "running").length;
  const statuses = state.songs.map(songState);
  elements["metric-pending"].textContent = String(running);
  elements["metric-success"].textContent = String(statuses.filter((status) => status === "success" || status === "skipped").length);
  elements["metric-skip"].textContent = String(statuses.filter((status) => status === "skipped").length);
  elements["metric-fail"].textContent = String(statuses.filter((status) => status === "failed" || status === "generation_limit" || status === "login_required").length);
  elements["metric-step"].textContent = state.current?.account_id === state.accountId ? state.current.current_step : "-";
}

function renderControls() {
  const running = isRunning();
  const pipelineBusy = pipelineWorkflowBusy();
  for (const id of ["account-new", "account-cancel", "account-copy", "select-all", "select-failed", "refresh-songs", "start-run"]) {
    elements[id].disabled = running || pipelineBusy;
  }
  elements["account-copy"].disabled = running || pipelineBusy || !state.accountId;
  elements["pause-run"].disabled = !running || state.current?.status !== "running";
  elements["resume-run"].disabled = !running || state.current?.status !== "paused";
  elements["stop-run"].disabled = !running;
  elements["fresh-run"].disabled = running;
  const modelLocked = running || pipelineBusy;
  renderGenerationModelControls(modelLocked);
  const account = state.accounts.find((item) => item.id === state.accountId);
  const lyricDirDirty = Boolean(account) && elements["lyric-dir-input"].value.trim() !== account.lyric_dir;
  elements["apply-lyric-dir"].disabled = running || pipelineBusy || !state.accountId;
  elements["refresh-songs"].disabled = running || pipelineBusy || lyricDirDirty;
  if (lyricDirDirty || pipelineBusy) elements["start-run"].disabled = true;
  elements["account-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  elements["settings-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  elements["ai-settings-form"].querySelectorAll("input").forEach((input) => input.disabled = running);
  elements["test-ai-settings"].disabled = running;
  document.querySelectorAll("[data-edit-ai-config]").forEach((button) => button.disabled = running || uploadRunning());
  elements["ai-config-cancel"].disabled = running;
  elements["save-settings"].disabled = running;
  document.querySelectorAll("[data-edit-account]").forEach((button) => button.disabled = running);
  document.querySelectorAll("[data-delete-account]").forEach((button) => button.disabled = running || uploadRunning());
  document.querySelectorAll("[data-login-account]").forEach((button) => button.disabled = running || uploadRunning());
  document.querySelectorAll("[data-close-browser-account]").forEach((button) => button.disabled = running || uploadRunning());
  renderAccountMenu();
  renderUploadRun();
  renderLyricControls();
  renderPipelinePanel();
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
  if (state.editingAccountId && !state.accounts.some((account) => account.id === state.editingAccountId)) {
    state.editingAccountId = "";
    state.accountEditorOpen = false;
  }
  renderAccounts();
  const account = state.accounts.find((item) => item.id === state.accountId);
  fillAccountForm(account);
  await reloadAccountWorkspace();
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
  if (!runMatchesCurrentAccount(state.uploadRun)) state.uploadRun = null;
  renderPipelinePanel();
  renderCurrent();
  renderUploadRun();

  const isStale = () => reloadId !== state.accountReloadId;
  if (accountId) await loadSongs();
  else renderSongs();
  if (isStale()) return;

  await loadLyricTemplates().catch(() => {});
  if (isStale()) return;

  await loadUploads();
  if (isStale()) return;

  await loadPipelineRun();
  if (isStale()) return;

  await loadPipelineQueueOptions();
  if (isStale()) return;

  await loadPipelineQueue();
  if (isStale()) return;

  await loadCurrent();
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
  const limit = state.uploads?.batch_size || 10;
  if (state.uploadSelectionAccountId !== state.accountId) {
    state.uploadSelectionAccountId = state.accountId;
    state.uploadSelectionTouched = false;
    state.selectedUploads = new Set(files.slice(0, limit).map((file) => file.file_name));
  } else {
    const available = new Set(files.map((file) => file.file_name));
    state.selectedUploads = new Set([...state.selectedUploads].filter((name) => available.has(name)));
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

async function loadSettings() {
  state.settings = await api("/api/settings");
  state.lyricSystemPrompt = state.settings.ai_system_prompt;
  for (const form of [elements["settings-form"], elements["ai-settings-form"]]) {
    for (const key of Object.keys(state.settings)) {
      if (form.elements[key]) form.elements[key].value = state.settings[key];
    }
  }
  state.aiConfigEditorOpen = !(state.settings.ai_api_base_url && state.settings.ai_model);
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
    if (message.type === "upload_status") {
      if (runMatchesCurrentAccount(message.data)) {
        state.uploadRun = message.data;
        renderUploadRun();
        renderTaskStatus();
        syncPipelineAfterSingleStage(state.uploadRun);
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
      if (runMatchesCurrentAccount(message.data)) {
        applyCurrentRun(message.data);
        syncPipelineAfterSingleStage(state.current);
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
  restoreGenerationModel();
  restoreGenerationSinger();
  renderGenerationModelControls();
  bindEvents();
  renderView();
  await Promise.allSettled([loadHealth(), loadSettings()]);
  await loadAccounts();
  await loadLoginBrowser();
  const recent = await api("/api/logs/recent").catch(() => []);
  for (const event of recent) if (event.type === "log") appendLog(event.data);
  connectSocket();
  setInterval(loadHealth, 5000);
  setInterval(loadLoginBrowser, 5000);
  setInterval(loadUploads, 10000);
  setInterval(loadUploadRun, 5000);
  setInterval(loadPipelineRun, 5000);
  setInterval(loadPipelineQueue, 5000);
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
  elements["account-menu-button"].addEventListener("click", (event) => {
    event.stopPropagation();
    setAccountMenuOpen(!state.accountMenuOpen);
    if (state.accountMenuOpen) elements["account-menu"].querySelector("button")?.focus();
  });

  elements["account-menu"].addEventListener("click", (event) => {
    event.stopPropagation();
    const option = event.target.closest("[data-account-menu-id]");
    if (!option || accountMenuDisabled()) return;
    elements["account-select"].value = option.dataset.accountMenuId;
    setAccountMenuOpen(false);
    elements["account-select"].dispatchEvent(new Event("change", { bubbles: true }));
  });

  document.addEventListener("click", () => {
    if (state.accountMenuOpen) setAccountMenuOpen(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !state.accountMenuOpen) return;
    setAccountMenuOpen(false);
    elements["account-menu-button"].focus();
  });

  elements["account-menu-button"].addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    if (!state.accountMenuOpen) setAccountMenuOpen(true);
    const options = [...elements["account-menu"].querySelectorAll("button")];
    options[event.key === "ArrowDown" ? 0 : options.length - 1]?.focus();
  });

  elements["account-menu"].addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const options = [...elements["account-menu"].querySelectorAll("button")];
    const currentIndex = options.indexOf(document.activeElement);
    let nextIndex = 0;
    if (event.key === "ArrowDown") nextIndex = (currentIndex + 1) % options.length;
    if (event.key === "ArrowUp") nextIndex = (currentIndex - 1 + options.length) % options.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = options.length - 1;
    options[nextIndex]?.focus();
  });

  document.querySelectorAll(".nav-item:not(.is-disabled)").forEach((item) => {
    item.addEventListener("click", () => {
      state.view = item.dataset.view;
      if (state.view === "task" && state.stage === "lyrics") {
        state.stage = "generation";
      }
      renderView();
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
    const limit = state.uploads?.batch_size || 10;
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
    const limit = state.uploads?.batch_size || 10;
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
    if (!state.accountId) return toast("请先选择账号", true);
    try {
      state.uploadRun = await api(
        `/api/uploads/runs?account_id=${encodeURIComponent(state.accountId)}&day=${encodeURIComponent(todayValue())}`,
        {
          method: "POST",
          body: JSON.stringify({
            file_names: [...state.selectedUploads],
            ai_created: state.uploadAiCreated,
            auto_replace_noncompliant: state.autoReplaceNoncompliant,
          }),
        },
      );
      renderUploadRun();
      toast("上传任务已启动");
    } catch (error) { toast(error.message, true); }
  });

  elements["retry-rejected-upload"].addEventListener("click", async () => {
    if (!state.accountId) return toast("请先选择账号", true);
    const regenerateCount = state.uploads?.files?.length || 0;
    if (!regenerateCount) return toast("没有待发布的歌曲", true);
    try {
      state.uploadRun = await api(
        `/api/uploads/runs/retry-rejected?account_id=${encodeURIComponent(state.accountId)}&day=${encodeURIComponent(todayValue())}`,
        {
          method: "POST",
          body: JSON.stringify({
            ai_created: state.uploadAiCreated,
            model_name: state.generationModel || "自动",
            singer_name: elements["generation-singer"].value,
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
    try {
      state.uploadRun = await api("/api/uploads/runs/stop", { method: "POST" });
      renderUploadRun(); toast("已请求停止上传");
    } catch (error) { toast(error.message, true); }
  });

  elements["pipeline-queue-list"].addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-queue-account]");
    if (!checkbox || checkbox.disabled) return;
    if (checkbox.checked) state.selectedPipelineQueueAccounts.add(checkbox.dataset.queueAccount);
    else state.selectedPipelineQueueAccounts.delete(checkbox.dataset.queueAccount);
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
    state.selected = new Set(state.songs.filter((song) => !song.valid || songState(song) === "failed").map((song) => song.file_name));
    renderSongs();
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
    if (!state.accountId) return toast("请先选择账号", true);
    if (!state.selected.size) return toast("请选择歌词文件", true);
    try {
      state.current = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          account_id: state.accountId,
          song_files: [...state.selected],
          day: todayValue(),
          fresh_run: elements["fresh-run"].checked,
          model_name: state.generationModel || elements["generation-model"].value,
          singer_name: elements["generation-singer"].value,
        }),
      });
      applyCurrentRun(state.current, { immediate: true });
      if (!["completed", "failed", "stopped", "generation_limit"].includes(state.current.status)) {
        toast("任务已启动");
      }
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
    const form = runtimeActive ? elements["settings-form"] : elements["ai-settings-form"];
    const payload = {};
    const numberFields = new Set([
      "ai_max_retries",
    ]);
    for (const input of form.elements) {
      if (!input.name) continue;
      payload[input.name] = runtimeActive || numberFields.has(input.name)
        ? Number(input.value)
        : input.value.trim();
    }
    try {
      state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      if (!runtimeActive) state.aiConfigEditorOpen = false;
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

  elements["ai-config-cards"].addEventListener("click", (event) => {
    const button = event.target.closest("[data-edit-ai-config]");
    if (!button || button.disabled) return;
    state.aiConfigEditorOpen = true;
    renderSettingsTabs();
    elements["ai-settings-form"].ai_api_base_url.focus();
  });

  elements["ai-config-cancel"].addEventListener("click", () => {
    if (!state.settings?.ai_api_base_url || !state.settings?.ai_model) return;
    state.aiConfigEditorOpen = false;
    for (const [key, value] of Object.entries(state.settings)) {
      if (elements["ai-settings-form"].elements[key]) elements["ai-settings-form"].elements[key].value = value;
    }
    renderSettingsTabs();
  });

  elements["test-ai-settings"].addEventListener("click", async () => {
    const form = elements["ai-settings-form"];
    const payload = {
      ai_api_base_url: form.ai_api_base_url.value.trim(),
      ai_api_key: form.ai_api_key.value.trim(),
      ai_model: form.ai_model.value.trim(),
    };
    if (!payload.ai_api_base_url || !payload.ai_model) {
      return toast("请先填写 API 地址和模型", true);
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
