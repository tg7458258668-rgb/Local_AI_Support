const chatBox = document.getElementById("chat-box");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const debugToggle = document.getElementById("debug-toggle");
const channelInput = document.getElementById("channel-input");
const userIdInput = document.getElementById("user-id-input");
const customerSelect = document.getElementById("customer-select");
const newCustomerBtn = document.getElementById("new-customer-btn");
const reloadCustomersBtn = document.getElementById("reload-customers-btn");
const conversationIdInput = document.getElementById("conversation-id-input");
const memoryStatus = document.getElementById("memory-status");
const memorySummary = document.getElementById("memory-summary");
const refreshMemoryBtn = document.getElementById("refresh-memory-btn");
const learnedCount = document.getElementById("learned-count");
const gapStatus = document.getElementById("gap-status");
const testDebugDetails = document.getElementById("test-debug-details");
const modelStatus = document.getElementById("model-status");
const modelTestMode = document.getElementById("model-test-mode");
const modelAInput = document.getElementById("model-a-input");
const modelBInput = document.getElementById("model-b-input");
const refreshModelsBtn = document.getElementById("refresh-models-btn");
const ADMIN_API = "/api/v1/admin";

let modelState = {
  settings: {},
  models: []
};

let customerMemories = [];
let lastQuestionText = "";

const FEEDBACK_LABELS = {
  good: "好回答",
  factual_error: "事实错误",
  missing_knowledge: "资料缺失",
  wrong_retrieval: "检索错误",
  style_issue: "话术不好",
  bad_quote: "报价问题",
  needs_review: "待复核"
};

function escapeHtml(text) {
  if (text === null || text === undefined) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function safeText(text) {
  return text === null || text === undefined ? "" : String(text);
}

function formatScore(value) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  return Number.isNaN(num) ? String(value) : num.toFixed(3);
}

function formatElapsed(ms) {
  if (ms === null || ms === undefined || ms === "") return "-";
  const num = Number(ms);
  if (Number.isNaN(num)) return String(ms);
  if (num < 1000) return `${Math.round(num)} ms`;
  return `${(num / 1000).toFixed(2)} 秒`;
}

function formatRichText(text) {
  if (text === null || text === undefined) return "";

  let safe = escapeHtml(String(text));
  safe = safe.replace(/\n{3,}/g, "\n\n");
  safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  const blocks = [];
  let paragraph = [];
  let list = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${paragraph.join("<br>")}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    blocks.push(`<ul>${list.map(item => `<li>${item}</li>`).join("")}</ul>`);
    list = [];
  };

  safe.split("\n").forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      return;
    }
    const bullet = line.match(/^[-•]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      return;
    }
    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();
  return blocks.join("") || "<p></p>";
}

function formatMatchedRule(matchedRule) {
  if (!matchedRule) return "无";
  if (typeof matchedRule === "string") return matchedRule;
  if (typeof matchedRule === "object") return matchedRule.rule_name || matchedRule.id || "无";
  return "无";
}

function formatHint(data) {
  if (data.hint) return data.hint;
  if (data.tip) return data.tip;
  if (data.note) return data.note;
  if (data.human_check) return data.human_check;
  if (data.need_human === true || data.need_handoff === true || data.should_human_confirm === true) {
    return "本回答建议人工进一步确认";
  }
  return "当前未触发人工接管提示";
}

function getDebugMode() {
  return localStorage.getItem("chat_debug_mode") === "1";
}

function setDebugMode(enabled) {
  localStorage.setItem("chat_debug_mode", enabled ? "1" : "0");
}

function syncDebugVisibility() {
  const enabled = getDebugMode();
  if (testDebugDetails) testDebugDetails.classList.toggle("hidden", !enabled);
  document.querySelectorAll(".msg-meta").forEach(el => {
    if (enabled) el.classList.remove("hidden");
    else el.classList.add("hidden");
  });
}

function getTesterConfig() {
  return {
    channel: channelInput?.value || "api",
    user_id: userIdInput?.value.trim() || "",
    conversation_id: conversationIdInput?.value.trim() || "",
    model_mode: modelTestMode?.value || "single",
    model_a: modelAInput?.value || "",
    model_b: modelBInput?.value || ""
  };
}

function makeCustomerId() {
  const stamp = new Date();
  const date = [
    stamp.getFullYear(),
    String(stamp.getMonth() + 1).padStart(2, "0"),
    String(stamp.getDate()).padStart(2, "0")
  ].join("");
  const suffix = Math.random().toString(36).slice(2, 6);
  return `customer_${date}_${suffix}`;
}

function saveTesterConfig() {
  const config = getTesterConfig();
  localStorage.setItem("chat_test_channel", config.channel);
  localStorage.setItem("chat_test_user_id", config.user_id);
  localStorage.setItem("chat_test_conversation_id", config.conversation_id);
  localStorage.setItem("chat_model_test_mode", config.model_mode);
  localStorage.setItem("chat_model_a", config.model_a);
  localStorage.setItem("chat_model_b", config.model_b);
  updateMemoryStatus();
}

function loadTesterConfig() {
  if (channelInput) channelInput.value = localStorage.getItem("chat_test_channel") || "api";
  if (userIdInput) {
    let userId = localStorage.getItem("chat_test_user_id") || "";
    if (!userId) {
      userId = makeCustomerId();
      localStorage.setItem("chat_test_user_id", userId);
    }
    userIdInput.value = userId;
  }
  if (conversationIdInput) {
    let conversationId = localStorage.getItem("chat_test_conversation_id") || "";
    if (!conversationId) {
      conversationId = `demo_session_${Date.now().toString(36)}`;
      localStorage.setItem("chat_test_conversation_id", conversationId);
    }
    conversationIdInput.value = conversationId;
  }
  if (modelTestMode) modelTestMode.value = localStorage.getItem("chat_model_test_mode") || "single";
  updateMemoryStatus();
  syncCompareMode();
}

function customerLabel(item) {
  if (!item) return "";
  const name = item.customer_name || item.user_id || "未命名客户";
  const bits = [name];
  if (item.scenario) bits.push(item.scenario);
  if (item.budget) bits.push(`预算 ${item.budget}`);
  return bits.join(" ｜ ");
}

function renderCustomerSelect() {
  if (!customerSelect) return;
  const config = getTesterConfig();
  const channel = config.channel;
  const currentId = config.user_id;
  const seen = new Set();
  const options = [];
  const currentMemory = customerMemories.find((item) => item.channel === channel && item.user_id === currentId);
  const rows = currentMemory
    ? [currentMemory, ...customerMemories.filter((item) => !(item.channel === channel && item.user_id === currentId))]
    : customerMemories;

  if (currentId) {
    options.push(`<option value="${escapeHtml(currentId)}">${escapeHtml(currentMemory ? customerLabel(currentMemory) : `${currentId} ｜ 当前客户`)}</option>`);
    seen.add(currentId);
  }
  for (const item of rows) {
    if (item.channel !== channel || !item.user_id || seen.has(item.user_id)) continue;
    seen.add(item.user_id);
    options.push(`<option value="${escapeHtml(item.user_id)}">${escapeHtml(customerLabel(item))}</option>`);
  }
  customerSelect.innerHTML = options.join("") || `<option value="">暂无客户，点击新增客户</option>`;
  customerSelect.value = currentId || "";
}

async function loadCustomerMemories(q = "") {
  if (customerSelect) {
    customerSelect.innerHTML = `<option value="">正在读取客户...</option>`;
  }
  try {
    const resp = await fetch(`${ADMIN_API}/memories${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.status);
    customerMemories = Array.isArray(data.items) ? data.items : [];
    renderCustomerSelect();
  } catch (err) {
    if (customerSelect) {
      customerSelect.innerHTML = `<option value="">客户列表读取失败</option>`;
    }
  }
}

async function ensureCustomerMemory(userId, channel) {
  const existing = customerMemories.find((item) => item.channel === channel && item.user_id === userId);
  if (existing) return existing;
  const payload = {
    channel,
    user_id: userId,
    customer_name: "",
    contact: "",
    products: [],
    preferences: [],
    common_questions: [],
    risk_flags: [],
    scenario: "",
    budget: "",
    project_time: "",
    decision_status: "",
    concerns: [],
    quoted_schemes: [],
    notes: "",
    live_room_area: "",
    camera_count: "",
    robot_arm_count: "",
    track_preference: ""
  };
  const resp = await fetch(`${ADMIN_API}/memories/${encodeURIComponent(channel)}/${encodeURIComponent(userId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await resp.json();
  if (!resp.ok || data.ok === false) throw new Error(data.detail || data.error || resp.status);
  return data.item || data;
}

async function createNewCustomer() {
  const channel = channelInput?.value || "api";
  const userId = makeCustomerId();
  if (userIdInput) userIdInput.value = userId;
  if (conversationIdInput) {
    const conversationId = `session_${Date.now().toString(36)}`;
    conversationIdInput.value = conversationId;
    localStorage.setItem("chat_test_conversation_id", conversationId);
  }
  saveTesterConfig();
  try {
    await ensureCustomerMemory(userId, channel);
    await loadCustomerMemories();
    renderMemorySummary(null);
    updateMemoryStatus();
  } catch (err) {
    if (memoryStatus) {
      memoryStatus.textContent = `新增客户失败：${err.message || err}`;
      memoryStatus.className = "panel-subtitle muted";
    }
  }
}

function selectCustomer(userId) {
  if (!userId) return;
  if (userIdInput) userIdInput.value = userId;
  if (conversationIdInput) {
    const conversationId = `session_${userId}_${Date.now().toString(36)}`.replace(/[^A-Za-z0-9_-]/g, "_");
    conversationIdInput.value = conversationId;
  }
  saveTesterConfig();
  renderCustomerSelect();
  refreshCurrentMemory();
}

function syncCompareMode() {
  const compare = (modelTestMode?.value || "single") === "compare";
  document.querySelectorAll(".compare-only").forEach((el) => el.classList.toggle("hidden", !compare));
}

function populateModelSelects() {
  const options = modelState.models.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join("");
  const current = modelState.settings.chat_model || "";
  for (const select of [modelAInput, modelBInput]) {
    if (!select) continue;
    select.innerHTML = options || `<option value="">未读取到模型</option>`;
  }
  if (modelAInput) modelAInput.value = localStorage.getItem("chat_model_a") || current;
  if (modelBInput) {
    const savedB = localStorage.getItem("chat_model_b") || "";
    const fallbackB = modelState.models.find((item) => item.name !== modelAInput?.value)?.name || current;
    modelBInput.value = savedB || fallbackB;
  }
}

async function loadModels() {
  if (modelStatus) modelStatus.textContent = "正在读取当前模型...";
  try {
    const resp = await fetch(`${ADMIN_API}/models`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.status);
    modelState.settings = data.settings || {};
    modelState.models = Array.isArray(data.ollama?.models) ? data.ollama.models : [];
    populateModelSelects();
    if (modelStatus) {
      const installed = modelState.models.length;
      const chat = modelState.settings.chat_model || "-";
      const embed = modelState.settings.embed_model || "-";
      modelStatus.textContent = data.ollama?.online
        ? `当前回答模型：${chat}｜向量模型：${embed}｜已安装 ${installed} 个模型`
        : `Ollama 离线：${data.ollama?.error || "-"}`;
    }
  } catch (err) {
    if (modelStatus) modelStatus.textContent = `模型读取失败：${err}`;
  }
}

function updateMemoryStatus() {
  if (!memoryStatus) return;
  const config = getTesterConfig();
  if (!config.user_id) {
    memoryStatus.textContent = config.conversation_id
      ? `当前会话：${config.channel} / ${config.conversation_id}，会保留本轮上下文。`
      : "未填写客户 ID 或会话 ID，不会保留上下文。";
    memoryStatus.className = config.conversation_id ? "panel-subtitle active" : "panel-subtitle muted";
    return;
  }
  memoryStatus.textContent = `当前客户：${config.channel} / ${config.user_id}，本轮会读写长期记忆。`;
  memoryStatus.className = "panel-subtitle active";
}

function listText(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return values.filter(Boolean).join("、");
}

function memoryRows(memory) {
  if (!memory || typeof memory !== "object") return [];
  return [
    ["称呼", memory.customer_name],
    ["联系方式", memory.contact],
    ["产品", listText(memory.products)],
    ["偏好", listText(memory.preferences)],
    ["场景", memory.scenario],
    ["预算", memory.budget],
    ["项目时间", memory.project_time],
    ["决策状态", memory.decision_status],
    ["直播间面积", memory.live_room_area],
    ["机位数量", memory.camera_count],
    ["机械臂数量", memory.robot_arm_count],
    ["轨道需求", memory.track_preference],
    ["关注点", listText(memory.concerns)],
    ["风险标记", listText(memory.risk_flags)],
    ["历史报价", listText(memory.quoted_schemes)],
    ["更新时间", memory.updated_at]
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
}

function renderMemorySummary(memory) {
  if (!memorySummary) return;
  const rows = memoryRows(memory);
  if (!rows.length) {
    memorySummary.className = "memory-summary empty";
    memorySummary.textContent = getTesterConfig().user_id
      ? "当前客户暂时没有画像，发送包含称呼、预算、场景、产品偏好的消息后会更新。"
      : "当前没有加载客户画像。";
    return;
  }
  memorySummary.className = "memory-summary";
  memorySummary.innerHTML = rows
    .map(([label, value]) => `<span class="memory-chip"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</span>`)
    .join("");
}

async function refreshCurrentMemory() {
  const config = getTesterConfig();
  saveTesterConfig();
  if (!config.user_id) {
    renderMemorySummary(null);
    return;
  }
  if (memorySummary) {
    memorySummary.className = "memory-summary empty";
    memorySummary.textContent = "正在读取客户画像...";
  }
  try {
    const resp = await fetch(`${ADMIN_API}/memories?q=${encodeURIComponent(config.user_id)}`);
    const data = await resp.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const item = items.find(x => x.channel === config.channel && x.user_id === config.user_id) || null;
    if (item) {
      const key = `${item.channel}:${item.user_id}`;
      const others = customerMemories.filter((row) => `${row.channel}:${row.user_id}` !== key);
      customerMemories = [item, ...others];
      renderCustomerSelect();
    }
    renderMemorySummary(item);
  } catch (err) {
    if (memorySummary) {
      memorySummary.className = "memory-summary empty error";
      memorySummary.textContent = `读取客户画像失败：${err}`;
    }
  }
}

async function refreshLearnedKnowledgeCount() {
  if (!learnedCount) return;
  try {
    const resp = await fetch(`${ADMIN_API}/learned-knowledge`);
    const data = await resp.json();
    learnedCount.textContent = `${Number(data.total || 0)} 条`;
  } catch (err) {
    learnedCount.textContent = "读取失败";
  }
}

function dedupeSources(sources) {
  const map = new Map();

  for (const item of sources || []) {
    const key = [
      item.type || "",
      item.doc_name || "",
      item.section || "",
      item.source || "",
      item.question || ""
    ].join("||");

    const oldItem = map.get(key);
    const oldScore = Number(oldItem?.score ?? -1);
    const newScore = Number(item?.score ?? -1);

    if (!oldItem || newScore > oldScore) {
      map.set(key, item);
    }
  }

  return Array.from(map.values()).sort((a, b) => Number(b.score ?? -1) - Number(a.score ?? -1));
}

function buildSourceText(source) {
  const parts = [];
  const firstLabel =
    source.route?.toUpperCase() ||
    source.type?.toUpperCase() ||
    (source.doc_name ? "DOC" : "FAQ");

  parts.push(firstLabel);
  if (source.doc_name) parts.push(`文档: ${source.doc_name}`);
  if (source.category) parts.push(`类别: ${source.category}`);
  if (source.section) parts.push(`章节: ${source.section}`);
  if (source.source) parts.push(`来源: ${source.source}`);
  if (source.question) parts.push(`问题: ${source.question}`);
  if (source.score !== undefined && source.score !== null) {
    parts.push(`分数: ${formatScore(source.score)}`);
  }

  return parts.join(" | ");
}

function buildTimingRows(timings) {
  if (!timings || typeof timings !== "object") return "";

  const rows = [
    ["记忆读写耗时", timings.memory_ms],
    ["历史读取耗时", timings.history_ms],
    ["上下文规划耗时", timings.context_plan_ms],
    ["规则匹配耗时", timings.rule_match_ms],
    ["FAQ检索耗时", timings.faq_retrieval_ms],
    ["DOC检索耗时", timings.doc_retrieval_ms],
    ["路由判断耗时", timings.route_decision_ms],
    ["答案生成耗时", timings.answer_generation_ms],
    ["来源整理耗时", timings.source_format_ms],
    ["总耗时", timings.total_ms],
    ["检索缓存命中", timings.retrieval_cache_hit === true ? "是" : timings.retrieval_cache_hit === false ? "否" : undefined]
  ];

  return rows
    .map(([label, value]) => {
      if (value === undefined) return "";
      return `<div class="meta-row"><strong>${escapeHtml(label)}：</strong>${escapeHtml(formatElapsed(value))}</div>`;
    })
    .join("");
}

function buildDebugSection(title, html) {
  if (!html) return "";
  return `
    <details class="debug-section">
      <summary>${escapeHtml(title)}</summary>
      <div class="debug-body">${html}</div>
    </details>
  `;
}

function buildKeyValueRows(rows) {
  return rows
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([label, value]) => `<div class="meta-row"><strong>${escapeHtml(label)}：</strong>${escapeHtml(value)}</div>`)
    .join("");
}

function responseSnapshot(data, question) {
  return {
    message: question || data.message || lastQuestionText || "",
    answer: data.answer || data.response || "",
    route: data.route || "",
    need_human: Boolean(data.need_human),
    hint: formatHint(data),
    matched_rule: formatMatchedRule(data.matched_rule),
    faq_top_score: data.faq_top_score ?? data.faq_score ?? 0,
    doc_top_score: data.doc_top_score ?? data.doc_score ?? 0,
    sources: Array.isArray(data.sources) ? data.sources : [],
    retrieval_debug: Array.isArray(data.retrieval_debug) ? data.retrieval_debug : [],
    memory: data.memory || null,
    timings: data.timings || {},
    metadata: data.metadata || {},
    channel: data.channel || getTesterConfig().channel,
    user_id: data.user_id || getTesterConfig().user_id || "",
    conversation_id: data.conversation_id || getTesterConfig().conversation_id || ""
  };
}

function feedbackButtonsHtml(snapshot) {
  const payload = encodeURIComponent(JSON.stringify(snapshot));
  const buttons = ["good", "factual_error", "missing_knowledge", "wrong_retrieval", "style_issue", "bad_quote"]
    .map((verdict) => `<button class="feedback-chip" type="button" data-answer-feedback="${verdict}" data-feedback-snapshot="${payload}">${FEEDBACK_LABELS[verdict]}</button>`)
    .join("");
  return `
    <div class="answer-feedback-bar" aria-label="回答质量反馈">
      ${buttons}
      <button class="feedback-chip feedback-chip-strong" type="button" data-answer-feedback="good" data-feedback-regression="1" data-feedback-snapshot="${payload}">加入回归</button>
      <span class="feedback-status" aria-live="polite"></span>
    </div>
  `;
}

async function saveAnswerFeedback(verdict, snapshot, options = {}) {
  const payload = {
    message: snapshot.message || "",
    answer: snapshot.answer || "",
    verdict,
    notes: options.notes || "",
    route: snapshot.route || "",
    snapshot
  };
  const resp = await fetch(`${ADMIN_API}/answer-feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || resp.status);
  if (verdict === "style_issue" && options.notes) {
    const instruction = [
      "优化客服回答话术。",
      `客户问题：${snapshot.message || ""}`,
      `当前回答：${snapshot.answer || ""}`,
      `希望调整：${options.notes}`,
      "请生成可审核的回答风格或行为规则草稿，不要直接改变事实口径。"
    ].join("\n");
    const draftResp = await fetch(`${ADMIN_API}/tuning/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction })
    });
    const draftData = await draftResp.json();
    if (!draftResp.ok) throw new Error(draftData.detail || draftResp.status);
    data.tuning_draft = draftData.draft || null;
  }
  if (options.toRegression) {
    const convert = await fetch(`${ADMIN_API}/answer-feedback/${encodeURIComponent(data.item.id)}/regression-case`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const converted = await convert.json();
    if (!convert.ok) throw new Error(converted.detail || convert.status);
    data.regression = converted.item;
  }
  return data;
}

function buildMemoryDebug(memory) {
  const rows = memoryRows(memory);
  if (!rows.length) return `<div class="empty-debug">本轮没有客户记忆。填写客户 ID 后才会读写长期记忆。</div>`;
  return `<div class="debug-chip-list">${rows.map(([label, value]) => `
    <span class="debug-chip"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</span>
  `).join("")}</div>`;
}

function buildContextDebug(metadata) {
  const plan = metadata?.context_plan || {};
  const history = Array.isArray(metadata?.conversation_context) ? metadata.conversation_context : [];
  const rows = buildKeyValueRows([
    ["读取最近对话", plan.used_history ? "是" : "否"],
    ["读取客户记忆", plan.used_memory ? "是" : "否"],
    ["上下文追问", plan.contextual_query ? "是" : "否"],
    ["缓存策略", plan.cache_policy],
    ["直出回答", plan.direct_answer_allowed === false ? "已禁用" : "允许"],
    ["识别锚点", Array.isArray(plan.anchors) ? plan.anchors.join("、") : ""],
    ["判断原因", plan.reason],
    ["历史轮数", plan.history_turn_count]
  ]);
  const historyRows = history.slice(-6).map((item, index) => `
    <li>
      <strong>${index + 1}. ${escapeHtml(item.route || "-")}</strong>
      <div>客户：${escapeHtml(item.message || "")}</div>
      <div>客服：${escapeHtml(safeText(item.answer).slice(0, 120))}${safeText(item.answer).length > 120 ? "..." : ""}</div>
    </li>
  `).join("");
  return `
    ${rows || `<div class="empty-debug">本轮没有上下文规划信息。</div>`}
    ${historyRows ? `<div class="source-title">最近上下文</div><ul class="debug-list">${historyRows}</ul>` : `<div class="empty-debug">当前会话还没有可用的最近上下文。</div>`}
  `;
}

function buildQuoteDebug(metadata) {
  const draft = metadata?.quote_draft;
  if (!draft || typeof draft !== "object") return "";
  const quoteItems = Array.isArray(draft.quote_items) ? draft.quote_items : [];
  const sources = Array.isArray(draft.sources) ? draft.sources : [];
  const approval = Array.isArray(draft.requires_confirmation)
    ? draft.requires_confirmation
    : Array.isArray(draft.approval_required)
      ? draft.approval_required
      : [];
  const products = Array.isArray(draft.recommended_products)
    ? draft.recommended_products.map((item) => {
      if (typeof item === "string") return item;
      if (!item || typeof item !== "object") return "";
      return [item.product, item.version].filter(Boolean).join(" ");
    }).filter(Boolean)
    : [];
  const rows = buildKeyValueRows([
    ["需求摘要", draft.need_summary],
    ["推荐产品", products.join("、")],
    ["参考总价", draft.reference_total],
    ["草案状态", draft.status],
    ["需人工确认", approval.join("、")],
    ["来源案例", sources.join("、")]
  ]);
  const itemHtml = quoteItems.length ? `
    <ul class="debug-list">
      ${quoteItems.map(item => `<li>${escapeHtml(item.name || "-")}：${escapeHtml(item.reference_price || "")}${item.note ? ` ｜ ${escapeHtml(item.note)}` : ""}</li>`).join("")}
    </ul>
  ` : "";
  return rows + itemHtml;
}

function buildLearningDebug(metadata) {
  const learning = metadata?.learning;
  if (!learning || typeof learning !== "object") {
    return `<div class="empty-debug">本轮没有触发纠错学习。测试页中说“你说错了，正确是...”会写入学习库。</div>`;
  }
  const item = learning.item || {};
  return buildKeyValueRows([
    ["学习开关", learning.enabled ? "启用" : "关闭"],
    ["识别纠错", learning.detected ? "是" : "否"],
    ["已写入", learning.saved ? "是" : "否"],
    ["已入向量库", learning.indexed === false ? "否" : learning.saved ? "是" : ""],
    ["学习项 ID", item.id],
    ["学到的事实", item.corrected_fact],
    ["问题线索", item.question_hint],
    ["分类", item.category],
    ["提示", learning.message],
    ["入库错误", learning.index_error]
  ]);
}

function buildGapDebug(metadata) {
  const gaps = metadata?.knowledge_gaps;
  if (!gaps || typeof gaps !== "object") {
    return `<div class="empty-debug">本轮没有主动调试信息。</div>`;
  }
  const gapItems = Array.isArray(gaps.gaps) ? gaps.gaps : [];
  const questions = Array.isArray(gaps.suggested_questions) ? gaps.suggested_questions : [];
  const docs = Array.isArray(gaps.needed_documents) ? gaps.needed_documents : [];
  const gapRows = gapItems.map(item => `<li>${escapeHtml(item.title || item.type || "-")}：${escapeHtml(item.detail || "")}</li>`).join("");
  const questionRows = questions.map(item => `<li>${escapeHtml(item)}</li>`).join("");
  const docRows = docs.map(item => `<li>${escapeHtml(item)}</li>`).join("");
  if (!gapRows && !questionRows && !docRows) {
    return `<div class="empty-debug">当前没有明显知识缺口。</div>`;
  }
  return `
    ${gapRows ? `<div class="source-title">知识缺口</div><ul class="debug-list">${gapRows}</ul>` : ""}
    ${questionRows ? `<div class="source-title">建议追问客户</div><ul class="debug-list">${questionRows}</ul>` : ""}
    ${docRows ? `<div class="source-title">建议补充资料</div><ul class="debug-list">${docRows}</ul>` : ""}
  `;
}

function renderGapStatus(metadata) {
  if (!gapStatus) return;
  const gaps = metadata?.knowledge_gaps;
  if (!gaps || typeof gaps !== "object") {
    gapStatus.textContent = "暂无主动调试信息";
    return;
  }
  const gapCount = Array.isArray(gaps.gaps) ? gaps.gaps.length : 0;
  const questionCount = Array.isArray(gaps.suggested_questions) ? gaps.suggested_questions.length : 0;
  const docCount = Array.isArray(gaps.needed_documents) ? gaps.needed_documents.length : 0;
  if (!gapCount && !questionCount && !docCount) {
    gapStatus.textContent = "当前没有明显缺口";
    return;
  }
  gapStatus.textContent = `缺口 ${gapCount} 个｜建议追问 ${questionCount} 个｜建议补资料 ${docCount} 个`;
}

function buildRetrievalDebug(data, sources) {
  const retrieval = Array.isArray(data.retrieval_debug) ? data.retrieval_debug : [];
  const sourceRows = sources.map(item => `<li>${escapeHtml(buildSourceText(item))}${item.reason ? ` ｜ ${escapeHtml(item.reason)}` : ""}</li>`).join("");
  const retrievalRows = retrieval.slice(0, 8).map(item => {
    const label = item.type || item.source_type || item.route || "hit";
    const score = item.adjusted_score ?? item.score;
    const reason = item.reason || item.hit_reason || "";
    const name = item.doc_name || item.source || item.question || item.title || item.category || "";
    return `<li>${escapeHtml(label)} ｜ ${escapeHtml(name)} ｜ 分数 ${escapeHtml(formatScore(score))}${reason ? ` ｜ ${escapeHtml(reason)}` : ""}</li>`;
  }).join("");
  if (!sourceRows && !retrievalRows) return `<div class="empty-debug">本轮没有检索命中调试信息。</div>`;
  return `
    ${sourceRows ? `<div class="source-title">回答来源</div><ul class="debug-list">${sourceRows}</ul>` : ""}
    ${retrievalRows ? `<div class="source-title">检索候选</div><ul class="debug-list">${retrievalRows}</ul>` : ""}
  `;
}

function buildModelDebug(metadata) {
  const models = metadata?.models;
  if (!models || typeof models !== "object") return "";
  return buildKeyValueRows([
    ["回答模型", models.chat_model],
    ["向量模型", models.embed_model],
    ["临时覆盖", models.override_used ? "是" : "否"]
  ]);
}

function scrollToBottom() {
  chatBox.scrollTop = chatBox.scrollHeight;
}

function appendUserMessage(text) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-user";
  wrap.innerHTML = `
    <div class="msg-bubble">
      <div class="msg-text">${escapeHtml(text)}</div>
    </div>
  `;
  chatBox.appendChild(wrap);
  scrollToBottom();
}

function appendLoadingMessage() {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-ai";
  wrap.id = "loading-message";
  wrap.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-bubble">
      <div class="msg-text msg-loading">正在生成回答</div>
    </div>
  `;
  chatBox.appendChild(wrap);
  scrollToBottom();
}

function appendCompareLoadingMessage(modelName) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-ai compare-loading-message";
  wrap.innerHTML = `
      <div class="msg-avatar">AI</div>
    <div class="msg-bubble">
      <div class="msg-text msg-loading">${escapeHtml(modelName)} 正在回答</div>
    </div>
  `;
  chatBox.appendChild(wrap);
  scrollToBottom();
}

function removeLoadingMessage() {
  const el = document.getElementById("loading-message");
  if (el) el.remove();
  document.querySelectorAll(".compare-loading-message").forEach((item) => item.remove());
}

function appendAiMessage(data, question = "") {
  const answer = data.answer || data.response || "暂无回答";
  const route = data.route || "-";
  const matchedRule = formatMatchedRule(data.matched_rule);
  const faqScore = formatScore(data.faq_score ?? data.faq_top_score);
  const docScore = formatScore(data.doc_score ?? data.doc_top_score);
  const hint = formatHint(data);
  const elapsedText = formatElapsed(data.elapsed_ms ?? data.timings?.total_ms);
  const debugMode = getDebugMode();
  const intentPlan = data.metadata?.intent_plan || {};

  const rawSources = Array.isArray(data.sources) ? data.sources : [];
  const sources = dedupeSources(rawSources);
  const timingRows = buildTimingRows(data.timings);

  const routeHtml = buildKeyValueRows([
    ["路由", route],
    ["需要人工", data.need_human ? "是" : "否"],
    ["规则命中", matchedRule],
    ["意图", intentPlan.intent || data.metadata?.intent || ""],
    ["意图置信度", formatScore(data.metadata?.intent_confidence ?? intentPlan.confidence)],
    ["意图来源", intentPlan.source],
    ["场景词", Array.isArray(data.metadata?.scenario_terms) ? data.metadata.scenario_terms.join("、") : ""],
    ["动作词", Array.isArray(data.metadata?.action_terms) ? data.metadata.action_terms.join("、") : ""],
    ["意图原因", data.metadata?.intent_reason || intentPlan.reason],
    ["FAQ分数", faqScore],
    ["DOC分数", docScore],
    ["提示", hint],
    ["渠道", data.channel],
    ["客户ID", data.user_id],
    ["会话ID", data.conversation_id]
  ]);
  const quoteHtml = buildQuoteDebug(data.metadata || {});
  const contextHtml = buildContextDebug(data.metadata || {});
  const retrievalHtml = buildRetrievalDebug(data, sources);
  const learningHtml = buildLearningDebug(data.metadata || {});
  const gapHtml = buildGapDebug(data.metadata || {});
  const modelHtml = buildModelDebug(data.metadata || {});
  const snapshot = responseSnapshot(data, question);

  renderMemorySummary(data.memory || null);
  renderGapStatus(data.metadata || {});
  refreshLearnedKnowledgeCount();

  const wrap = document.createElement("div");
  wrap.className = "msg msg-ai";
  wrap.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-bubble">
      <div class="msg-text">${formatRichText(answer)}</div>
      <div class="elapsed-line"><strong>接口总耗时：</strong>${escapeHtml(elapsedText)}</div>
      ${feedbackButtonsHtml(snapshot)}
      <div class="msg-meta ${debugMode ? "" : "hidden"}">
        ${buildDebugSection("路由与决策", routeHtml)}
        ${buildDebugSection("上下文检查", contextHtml)}
        ${modelHtml ? buildDebugSection("模型", modelHtml) : ""}
        ${buildDebugSection("客户记忆", buildMemoryDebug(data.memory))}
        ${buildDebugSection("纠错学习", learningHtml)}
        ${buildDebugSection("主动建议", gapHtml)}
        ${quoteHtml ? buildDebugSection("报价草案", quoteHtml) : ""}
        ${buildDebugSection("检索命中", retrievalHtml)}
        ${buildDebugSection("耗时", timingRows)}
      </div>
    </div>
  `;
  chatBox.appendChild(wrap);
  scrollToBottom();
}

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;
  lastQuestionText = question;

  appendUserMessage(question);
  questionInput.value = "";
  appendLoadingMessage();
  sendBtn.disabled = true;
  sendBtn.textContent = "发送中";
  saveTesterConfig();
  const config = getTesterConfig();
  const compareMode = config.model_mode === "compare";
  const models = compareMode
    ? [config.model_a, config.model_b].filter(Boolean)
    : [config.model_a].filter(Boolean);

  if (compareMode && models.length >= 2) {
    removeLoadingMessage();
    await sendCompareQuestions(question, config, models.slice(0, 2));
    sendBtn.disabled = false;
    sendBtn.textContent = "发送";
    return;
  }

  try {
    const resp = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: question,
        channel: config.channel,
        user_id: config.user_id || null,
        conversation_id: config.conversation_id || null,
        metadata: {
          test_page: true,
          model_override: config.model_a ? { chat_model: config.model_a } : undefined
        }
      })
    });

    const data = await resp.json();
    removeLoadingMessage();
    if (!resp.ok) {
      appendAiMessage({
        answer: `请求失败：${data.detail || resp.status}`,
        route: "error",
        matched_rule: "无",
        faq_top_score: 0,
        doc_top_score: 0,
        timings: {},
        hint: "请检查请求参数或后端服务",
        sources: []
      }, question);
      return;
    }
    appendAiMessage(data, question);
  } catch (err) {
    removeLoadingMessage();
    appendAiMessage({
      answer: `请求失败：${err}`,
      route: "-",
      matched_rule: "无",
      faq_score: "-",
      doc_score: "-",
      elapsed_ms: "-",
      timings: {},
      hint: "请检查后端服务是否正常运行",
      sources: []
    }, question);
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = "发送";
  }
}

async function sendCompareQuestions(question, config, models) {
  for (const [index, model] of models.entries()) {
    const compareRole = index === 0 ? "primary" : "shadow";
    appendCompareLoadingMessage(model);
    try {
      const resp = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question,
          channel: config.channel,
          user_id: null,
          conversation_id: config.conversation_id || null,
          metadata: {
            test_page: true,
            model_compare: true,
            model_compare_role: compareRole,
            regression_test: compareRole === "shadow",
            model_override: { chat_model: model }
          }
        })
      });
      const data = await resp.json();
      removeLoadingMessage();
      if (!resp.ok) {
        appendAiMessage({
          answer: `${model} 请求失败：${data.detail || resp.status}`,
          route: "error",
          matched_rule: "无",
          faq_top_score: 0,
          doc_top_score: 0,
          timings: {},
          hint: "请检查模型是否可用",
          sources: [],
          metadata: { models: { chat_model: model, embed_model: modelState.settings.embed_model, override_used: true } }
        }, question);
      } else {
        data.answer = `【${model}】\n${data.answer || ""}`;
        appendAiMessage(data, question);
      }
    } catch (err) {
      removeLoadingMessage();
      appendAiMessage({
        answer: `${model} 请求失败：${err}`,
        route: "error",
        matched_rule: "无",
        timings: {},
        hint: "请检查后端服务是否正常运行",
        sources: [],
        metadata: { models: { chat_model: model, embed_model: modelState.settings.embed_model, override_used: true } }
      }, question);
    }
  }
}

function resetChat() {
  chatBox.innerHTML = `
    <div class="msg msg-ai">
      <div class="msg-avatar">AI</div>
      <div class="msg-bubble">
        <div class="msg-text">
          你好，我是本地 AI 客服助手。你可以直接问我产品推荐、报价、保修和售后问题。
        </div>
      </div>
    </div>
  `;
  questionInput.value = "";
}

function useQuickPrompt(value) {
  if (!questionInput) return;
  questionInput.value = value || "";
  questionInput.focus();
}

sendBtn.addEventListener("click", sendQuestion);
clearBtn.addEventListener("click", resetChat);
if (refreshMemoryBtn) refreshMemoryBtn.addEventListener("click", refreshCurrentMemory);
if (refreshModelsBtn) refreshModelsBtn.addEventListener("click", loadModels);
if (newCustomerBtn) newCustomerBtn.addEventListener("click", createNewCustomer);
if (reloadCustomersBtn) reloadCustomersBtn.addEventListener("click", () => loadCustomerMemories());
if (customerSelect) {
  customerSelect.addEventListener("change", () => selectCustomer(customerSelect.value));
}
document.querySelectorAll("[data-quick-prompt]").forEach((button) => {
  button.addEventListener("click", () => useQuickPrompt(button.dataset.quickPrompt || ""));
});

chatBox.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-answer-feedback]");
  if (!button) return;
  const status = button.parentElement?.querySelector(".feedback-status");
  try {
    const snapshot = JSON.parse(decodeURIComponent(button.dataset.feedbackSnapshot || "%7B%7D"));
    button.disabled = true;
    if (status) status.textContent = "记录中...";
    const verdict = button.dataset.answerFeedback || "needs_review";
    let notes = "";
    if (verdict === "style_issue") {
      notes = window.prompt("请写一下希望怎么改话术，例如：更短一点、先给结论、少用内部词、不要像报价单。应用后台训练草稿后，下一次回答才会变化。") || "";
      if (!notes.trim()) {
        if (status) status.textContent = "已取消：需要填写希望调整的话术方向";
        return;
      }
    }
    const result = await saveAnswerFeedback(verdict, snapshot, {
      notes,
      toRegression: button.dataset.feedbackRegression === "1"
    });
    if (status) {
      status.textContent = result.tuning_draft
        ? "已记录，并生成训练草稿；到后台训练页应用后生效"
        : result.regression
          ? "已记录并加入回归"
          : "已记录反馈";
      status.className = "feedback-status success";
    }
  } catch (err) {
    if (status) {
      status.textContent = `记录失败：${err.message || err}`;
      status.className = "feedback-status error";
    }
  } finally {
    button.disabled = false;
  }
});

[channelInput, userIdInput, conversationIdInput, modelTestMode, modelAInput, modelBInput].forEach((input) => {
  if (!input) return;
  input.addEventListener("change", () => {
    saveTesterConfig();
    syncCompareMode();
    if (input === channelInput) {
      loadCustomerMemories();
    } else {
      renderCustomerSelect();
    }
    refreshCurrentMemory();
  });
  input.addEventListener("input", () => {
    saveTesterConfig();
    if (input === userIdInput) renderCustomerSelect();
  });
});

questionInput.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    sendQuestion();
  }
});

if (debugToggle) {
  debugToggle.checked = getDebugMode();
  debugToggle.addEventListener("change", () => {
    setDebugMode(debugToggle.checked);
    syncDebugVisibility();
  });
}

loadTesterConfig();
loadModels();
loadCustomerMemories();
refreshCurrentMemory();
refreshLearnedKnowledgeCount();
syncDebugVisibility();
