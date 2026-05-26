const ADMIN_API = "/api/v1/admin";
const CHAT_API = "/api/v1/chat";

const PAGE_META = {
  overview: {
    kicker: "Workbench",
    title: "总览",
    description: "从回答质量、知识索引、报价风险和回归测试看系统是否可靠。"
  },
  quality: {
    kicker: "QA workstation",
    title: "质检工作台",
    description: "按问答记录完成标注、修复动作和回归沉淀。"
  },
  regression: {
    kicker: "Regression",
    title: "回归测试",
    description: "验证关键问题的路由、工具、必含信息和人工复核策略。"
  },
  knowledge: {
    kicker: "Knowledge",
    title: "知识库中心",
    description: "维护 FAQ、文档、学习库，并确认 Qdrant 索引状态。"
  },
  sales: {
    kicker: "Quote rules",
    title: "报价规则",
    description: "维护内部报价规则、缺失字段、复核项和风险等级。"
  },
  memory: {
    kicker: "Customer memory",
    title: "客户记忆",
    description: "管理客户画像、产品偏好、预算、场景、历史报价和风险点。"
  },
  training: {
    kicker: "Training",
    title: "训练与测试",
    description: "生成规则草稿、运行回归测试、维护客服行为和话术。"
  },
  diagnostics: {
    kicker: "Diagnostics",
    title: "系统诊断",
    description: "查看 FastAPI、Ollama、Qdrant、模型、启动器和日志。"
  },
  settings: {
    kicker: "Advanced",
    title: "高级设置",
    description: "模型切换、原始 JSON 配置和高风险维护操作集中在这里。"
  }
};

const state = {
  page: document.body.dataset.page || "quality",
  summary: null,
  status: null,
  models: null,
  behaviorRules: {},
  answerStyles: {},
  quotePolicy: {},
  quoteCatalog: { arms: [], packages: [], options: [], rules: {}, updated_at: "" },
  pricingCatalog: { products: [], accessories: [], updated_at: "" },
  docs: [],
  faqs: [],
  rules: [],
  memories: [],
  learnedKnowledge: [],
  selectedFaq: null,
  selectedRule: null,
  selectedMemory: null,
  configQuoteDraft: null,
  trainingDraft: null,
  lastQualityResult: null,
  answerFeedback: [],
  qualityRecords: [],
  selectedQualityRecord: null,
  qualityFilter: "",
  regressionCases: [],
  regressionResults: [],
  knowledgeIndexStatus: null,
  selectedQuotePackageId: "",
  catalogFocus: { type: "package", id: "" },
  catalogEditor: null,
  docChunkModal: null,
  docPages: {}
};

function $(selector) {
  return document.querySelector(selector);
}

function $all(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function safeText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function escapeHtml(value) {
  return safeText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatMs(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return "-";
  if (n >= 1000) return `${(n / 1000).toFixed(1)} 秒`;
  return `${Math.round(n)} ms`;
}

function formatScore(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return "0.000";
  return n.toFixed(3);
}

function formatList(values, fallback = "-") {
  return Array.isArray(values) && values.length ? values.join("、") : fallback;
}

function splitWords(value) {
  return safeText(value)
    .split(/[\n,，、]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinWords(values) {
  return Array.isArray(values) ? values.join("、") : "";
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    data = {};
  }
  if (!res.ok) {
    throw new Error(data.detail || `请求失败：${res.status}`);
  }
  return data;
}

function setLoading(button, loadingText = "处理中...") {
  if (!button) return () => {};
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = loadingText;
  return () => {
    button.disabled = false;
    button.textContent = oldText;
  };
}

function showNotice(id, message, type = "info") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.className = `notice ${type}`;
  el.classList.remove("hidden");
}

function hideNotice(id) {
  document.getElementById(id)?.classList.add("hidden");
}

function statePill(label, type = "muted") {
  return `<span class="state-pill state-${type}">${escapeHtml(label)}</span>`;
}

function tag(label) {
  return `<span class="tag">${escapeHtml(label)}</span>`;
}

function tagList(items, fallback = "-") {
  const list = Array.isArray(items) ? items : (items ? [items] : []);
  if (!list.length) return escapeHtml(fallback);
  return list.slice(0, 8).map((item) => tag(safeText(item))).join("");
}

function formatJsonPreview(value) {
  if (!value || (Array.isArray(value) && !value.length)) return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (e) {
    return safeText(value);
  }
}

function cleanDocDisplayText(value) {
  return safeText(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => {
      if (!line) return false;
      if (/^\[OCR\s+page_\d+\.(?:png|jpg|jpeg)\]$/i.test(line)) return false;
      if (/^1st Art Company in CA$/i.test(line)) return false;
      if (/^H?U-?MOCO\.?$/i.test(line)) return false;
      if (/^[A-Z]\.$/.test(line)) return false;
      return true;
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function cleanDocLabel(value) {
  const text = cleanDocDisplayText(value).replace(/\s+/g, " ").trim();
  if (!text || /^[-{}[\]]+$/.test(text)) return "";
  if (/^(?:H?U-?MOCO|I\.?)$/i.test(text)) return "";
  return text;
}

function cleanDocList(items) {
  const list = Array.isArray(items) ? items : (items ? [items] : []);
  return Array.from(new Set(list.map(cleanDocLabel).filter(Boolean))).slice(0, 10);
}

function docTagList(items, fallback = "未识别") {
  const list = cleanDocList(items);
  if (!list.length) return `<span class="doc-empty-note">${escapeHtml(fallback)}</span>`;
  return `<div class="doc-readable-list">${list.map((item) => tag(item)).join("")}</div>`;
}

function humanTextBlock(value, fallback = "暂无可读内容") {
  const text = cleanDocDisplayText(value);
  return escapeHtml(text || fallback);
}

function formatDocValue(value, emptyText) {
  if (!value) return `<div class="doc-empty-note">${escapeHtml(emptyText)}</div>`;
  if (Array.isArray(value)) {
    const list = value.map(cleanDocLabel).filter(Boolean);
    if (!list.length) return `<div class="doc-empty-note">${escapeHtml(emptyText)}</div>`;
    return `<ul class="doc-bullet-list">${list.slice(0, 12).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value).filter(([, item]) => safeText(item).trim());
    if (!entries.length) return `<div class="doc-empty-note">${escapeHtml(emptyText)}</div>`;
    return `<div class="doc-kv-list">${entries.map(([key, item]) => `
      <div><span>${escapeHtml(key)}</span><strong>${escapeHtml(item)}</strong></div>
    `).join("")}</div>`;
  }
  const text = cleanDocLabel(value);
  return text ? escapeHtml(text) : `<div class="doc-empty-note">${escapeHtml(emptyText)}</div>`;
}

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return safeText(value);
  return `¥${Math.round(n).toLocaleString("zh-CN")}`;
}

function metricCard(label, value, note = "") {
  return `
    <div class="metric-card">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
      ${note ? `<div class="metric-note">${escapeHtml(note)}</div>` : ""}
    </div>
  `;
}

function statusCard(label, value, type = "muted", note = "") {
  return `
    <div class="status-card">
      <div class="entity-title-row">
        <div>
          <div class="status-label">${escapeHtml(label)}</div>
          ${note ? `<div class="status-note">${escapeHtml(note)}</div>` : ""}
        </div>
        ${statePill(value, type)}
      </div>
    </div>
  `;
}

function emptyState(text) {
  return `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function normalizePricingCatalog(catalog) {
  const source = catalog && typeof catalog === "object" ? catalog : {};
  return {
    products: Array.isArray(source.products) ? source.products : [],
    accessories: Array.isArray(source.accessories) ? source.accessories : [],
    updated_at: source.updated_at || ""
  };
}

function normalizeQuoteCatalog(catalog) {
  const source = catalog && typeof catalog === "object" ? catalog : {};
  return {
    version: source.version || 1,
    currency: source.currency || "CNY",
    arms: Array.isArray(source.arms) ? source.arms : [],
    packages: Array.isArray(source.packages) ? source.packages : [],
    options: Array.isArray(source.options) ? source.options : [],
    rules: source.rules && typeof source.rules === "object" ? source.rules : {},
    updated_at: source.updated_at || ""
  };
}

function onlineType(value) {
  return value === "online" ? "good" : "bad";
}

function runningType(value) {
  return value ? "good" : "bad";
}

function routeType(route, needHuman) {
  if (needHuman) return "warn";
  if (["faq", "doc", "quote_draft", "memory_recall", "learned_correction", "identity"].includes(route)) return "good";
  if (route === "fallback" || route === "error") return "bad";
  return "muted";
}

const ANSWER_FEEDBACK_LABELS = {
  good: "好回答",
  factual_error: "事实错误",
  missing_knowledge: "资料缺失",
  wrong_retrieval: "检索错误",
  style_issue: "话术不好",
  bad_quote: "报价问题",
  needs_review: "待复核"
};

function answerFeedbackType(verdict) {
  if (verdict === "good") return "good";
  if (verdict === "needs_review") return "warn";
  return "bad";
}

function compactKeywords(text) {
  const value = safeText(text).replace(/\s+/g, "");
  return value ? [value.slice(0, 12)] : [];
}

function qualitySnapshot(data) {
  return {
    message: $("#qualityQuestionInput")?.value.trim() || "",
    answer: data.answer || "",
    route: data.route || "",
    need_human: Boolean(data.need_human),
    hint: data.hint || "",
    matched_rule: data.matched_rule || "",
    faq_top_score: data.faq_top_score || 0,
    doc_top_score: data.doc_top_score || 0,
    sources: data.sources || [],
    retrieval_debug: data.retrieval_debug || [],
    memory: data.memory || null,
    timings: data.timings || {},
    metadata: data.metadata || {},
    channel: data.channel || "api",
    user_id: data.user_id || "",
    conversation_id: data.conversation_id || ""
  };
}

function sourceTitle(source) {
  if (source.type === "faq") return source.question || source.source || "FAQ";
  return source.doc_name || source.source || "文档";
}

function renderSources(sources = []) {
  if (!sources.length) return emptyState("本次没有返回回答来源。");
  return sources.slice(0, 6).map((item) => `
    <div class="source-card">
      <div class="entity-title-row">
        <strong>${escapeHtml(sourceTitle(item))}</strong>
        ${tag(item.type || "source")}
      </div>
      <div class="entity-meta">
        分数：${formatScore(item.adjusted_score ?? item.score)}
        ${item.category ? ` ｜ 分类：${escapeHtml(item.category)}` : ""}
        ${item.section ? ` ｜ 章节：${escapeHtml(item.section)}` : ""}
      </div>
      ${item.reason ? `<div class="entity-body">${escapeHtml(item.reason)}</div>` : ""}
    </div>
  `).join("");
}

function setPageShell() {
  const meta = PAGE_META[state.page] || PAGE_META.quality;
  $("#pageKicker").textContent = meta.kicker;
  $("#pageTitle").textContent = meta.title;
  $("#pageDescription").textContent = meta.description;
  document.title = `${meta.title} - AI 客服质检工作台`;

  $all(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.page === state.page);
  });
  $all(".page-section").forEach((section) => {
    section.classList.toggle("active", section.dataset.section === state.page);
  });
  renderFooterStatus();
}

function renderFooterStatus() {
  const fastapi = $("#footerFastapiStatus");
  const qdrant = $("#footerQdrantStatus");
  const ollama = $("#footerOllamaStatus");
  if (!fastapi || !qdrant || !ollama) return;
  const status = state.status || {};
  const models = state.models || {};
  const app = status.app || status;
  const qdrantInfo = status.qdrant || {};
  fastapi.textContent = app.running === false ? "offline" : "online";
  qdrant.textContent = qdrantInfo.running === false ? "offline" : "online";
  ollama.textContent = models.ollama?.online === false ? "offline" : (models.settings?.chat_model || "checking");
}

async function loadSummary() {
  state.summary = await fetchJson(`${ADMIN_API}/summary`);
  return state.summary;
}

async function loadStatus() {
  state.status = await fetchJson(`${ADMIN_API}/status`);
  return state.status;
}

async function loadModels() {
  state.models = await fetchJson(`${ADMIN_API}/models`);
  return state.models;
}

async function loadRegressionCases() {
  return await fetchJson(`${ADMIN_API}/regression-cases`);
}

function renderSummaryMetrics(targetId, summary = state.summary) {
  const el = document.getElementById(targetId);
  if (!el || !summary) return;
  el.innerHTML = [
    metricCard("文档", summary.doc_count || 0, "已入库文档"),
    metricCard("片段", summary.doc_chunk_count || 0, "用于检索"),
    metricCard("FAQ", summary.faq_count || 0, "标准问答"),
    metricCard("规则", summary.rule_count || 0, "路由与转人工")
  ].join("");
}

async function loadQualityPage() {
  const [summary, status, models, cases, feedback, qualityRecords] = await Promise.all([
    loadSummary(),
    loadStatus(),
    loadModels(),
    loadRegressionCases(),
    fetchJson(`${ADMIN_API}/answer-feedback`),
    fetchJson(`${ADMIN_API}/quality-records${state.qualityFilter ? `?flag=${encodeURIComponent(state.qualityFilter)}` : ""}`)
  ]);

  state.answerFeedback = feedback.items || [];
  state.qualityRecords = qualityRecords.items || [];
  renderSummaryMetrics("qualityMetricGrid", summary);
  renderQualitySystem(status, models);
  renderQualityRegression(cases);
  renderQualityKnowledge(summary);
  renderQualityTodos(summary, status, models, cases);
  renderQualityFeedbackList(state.answerFeedback);
  renderQualityRecordList(state.qualityRecords);
  renderQualityDrawer(state.selectedQualityRecord);
}

async function loadOverviewPage() {
  const [summary, status, models, records, indexStatus] = await Promise.all([
    loadSummary(),
    loadStatus(),
    loadModels(),
    fetchJson(`${ADMIN_API}/quality-records?status=pending`),
    fetchJson(`${ADMIN_API}/knowledge-index-status`)
  ]);
  renderSummaryMetrics("overviewMetricGrid", summary);
  state.qualityRecords = records.items || [];
  state.knowledgeIndexStatus = indexStatus;
  renderOverviewQuality(records.items || []);
  renderIndexStatus("overviewIndexStatus", indexStatus);
  renderFooterStatus();
  renderQualityTodos(summary, status, models, { items: [] });
}

function renderQualitySystem(status, models) {
  const ollama = models?.ollama || {};
  const settings = models?.settings || {};
  const el = $("#qualitySystemGrid");
  if (!el) return;
  el.innerHTML = [
    statusCard("FastAPI 后端", status.backend === "online" ? "在线" : "离线", onlineType(status.backend), status.base_dir || ""),
    statusCard("Ollama", status.ollama === "online" ? "在线" : "离线", onlineType(status.ollama), ollama.online ? `模型 ${ollama.models?.length || 0} 个` : ollama.error || ""),
    statusCard("Qdrant", status.qdrant === "online" ? "在线" : "离线", onlineType(status.qdrant), status.qdrant_storage_dir || ""),
    statusCard("回答模型", settings.chat_model || "-", settings.chat_model ? "good" : "warn", `向量：${settings.embed_model || "-"}`)
  ].join("");
}

function renderQualityRegression(cases) {
  const el = $("#qualityRegressionSummary");
  if (!el) return;
  const total = cases.total || cases.items?.length || 0;
  el.innerHTML = `
    <strong>当前测试用例 ${total} 条</strong>
    <div class="entity-meta">用于验证知识、记忆、报价与资料不足时的回答策略。</div>
  `;
}

function renderQualityKnowledge(summary) {
  const el = $("#qualityKnowledgePanel");
  if (!el) return;
  const docNames = Array.isArray(summary.doc_names) ? summary.doc_names : [];
  el.innerHTML = `
    ${statusCard("文档覆盖", `${summary.doc_count || 0} 个文档`, (summary.doc_count || 0) ? "good" : "warn", `${summary.doc_chunk_count || 0} 个检索片段`)}
    ${statusCard("FAQ 覆盖", `${summary.faq_count || 0} 条 FAQ`, (summary.faq_count || 0) ? "good" : "warn", "常见问法的第一道防线")}
    <div class="entity-card">
      <div class="entity-title">最近文档</div>
      <div class="entity-tags">${docNames.slice(0, 8).map(tag).join("") || tag("暂无文档")}</div>
    </div>
  `;
}

function renderQualityTodos(summary, status, models, cases) {
  const todos = [];
  if (status.ollama !== "online") todos.push(["检查 Ollama", "模型服务离线，测试问答会失败或变慢。", "bad"]);
  if (status.qdrant !== "online") todos.push(["检查 Qdrant", "向量库离线会影响 FAQ 和文档检索。", "bad"]);
  if (!summary.doc_count) todos.push(["上传产品资料", "当前没有文档，文档问答会缺少依据。", "warn"]);
  if (!summary.faq_count) todos.push(["补充 FAQ", "当前没有 FAQ，常见问题无法快速命中。", "warn"]);
  if (!cases.items?.length) todos.push(["建立回归测试", "没有测试集就难以判断调参是否变好。", "warn"]);
  const indexStatus = models?.settings?.embed_index_status;
  if (indexStatus && indexStatus !== "success") todos.push(["重建向量索引", `当前索引状态：${indexStatus}`, "warn"]);
  if (!todos.length) todos.push(["当前无阻塞项", "基础服务、知识和测试配置看起来可用。", "good"]);

  const el = $("#qualityTodoList");
  if (!el) return;
  el.innerHTML = todos.map(([title, body, type]) => `
    <div class="todo-item">
      <div class="entity-title-row">
        <strong>${escapeHtml(title)}</strong>
        ${statePill(type === "good" ? "正常" : type === "bad" ? "阻塞" : "建议", type)}
      </div>
      <div class="entity-meta">${escapeHtml(body)}</div>
    </div>
  `).join("");
}

async function runQualityTest(event) {
  event?.preventDefault();
  const question = $("#qualityQuestionInput")?.value.trim();
  if (!question) {
    $("#qualityResult").innerHTML = `<div class="notice error">请先输入客户问题。</div>`;
    return;
  }
  const restore = setLoading($("#qualityTestBtn"), "测试中...");
  $("#qualityResult").innerHTML = `<div class="notice loading">正在调用聊天接口并分析路由...</div>`;
  try {
    const payload = {
      message: question,
      channel: "api",
      user_id: $("#qualityUserInput")?.value.trim() || null,
      conversation_id: $("#qualityConversationInput")?.value.trim() || "admin-quality-check",
      metadata: { test_page: true }
    };
    const data = await fetchJson(CHAT_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    renderQualityResult(data);
  } catch (e) {
    $("#qualityResult").innerHTML = `<div class="notice error">测试失败：${escapeHtml(e.message)}</div>`;
    const badge = $("#qualityOverallBadge");
    if (badge) {
      badge.textContent = "测试失败";
      badge.className = "state-pill state-bad";
    }
  } finally {
    restore();
  }
}

function renderQualityResult(data) {
  state.lastQualityResult = data;
  const type = routeType(data.route, data.need_human);
  const badge = $("#qualityOverallBadge");
  if (badge) {
    badge.textContent = data.need_human ? "建议人工" : (type === "good" ? "可回答" : "需补资料");
    badge.className = `state-pill state-${type}`;
  }
  const gaps = data.metadata?.knowledge_gaps;
  const needed = gaps?.needed_document || gaps?.summary || data.hint || "";
  $("#qualityResult").innerHTML = `
    <div class="quality-result">
      <div class="score-strip">
        <div class="score-item"><span>路由</span><strong>${escapeHtml(data.route || "-")}</strong></div>
        <div class="score-item"><span>FAQ 分数</span><strong>${formatScore(data.faq_top_score)}</strong></div>
        <div class="score-item"><span>DOC 分数</span><strong>${formatScore(data.doc_top_score)}</strong></div>
        <div class="score-item"><span>总耗时</span><strong>${formatMs(data.timings?.total_ms)}</strong></div>
      </div>
      <div class="entity-card">
        <div class="entity-title-row">
          <strong>决策</strong>
          ${statePill(data.need_human ? "需要人工" : "自动回答", data.need_human ? "warn" : "good")}
        </div>
        <div class="entity-meta">
          命中规则：${escapeHtml(data.matched_rule || "无")} ｜ 提示：${escapeHtml(needed || "无")}
        </div>
      </div>
      <div>
        <h4>回答内容</h4>
        <div class="answer-box">${escapeHtml(data.answer || "")}</div>
      </div>
      <div>
        <h4>回答来源</h4>
        <div class="stack-list">${renderSources(data.sources || [])}</div>
      </div>
    </div>
  `;
  $("#qualityActionPanel")?.classList.remove("hidden");
}

function renderQualityFeedbackList(items = []) {
  const el = $("#qualityFeedbackList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无回答反馈。测试回答后可从质量动作区或对话窗口记录。");
    return;
  }
  el.innerHTML = items.slice(0, 20).map((item) => {
    const verdict = item.verdict || "needs_review";
    const hasCase = Boolean(item.regression_case_id);
    return `
      <div class="entity-card">
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.message || "-")}</h4>
          ${statePill(ANSWER_FEEDBACK_LABELS[verdict] || verdict, answerFeedbackType(verdict))}
        </div>
        <div class="entity-meta">route: ${escapeHtml(item.route || "-")} ｜ ${escapeHtml(item.created_at || "-")} ${hasCase ? "｜ 已加入回归" : ""}</div>
        <div class="entity-body">${escapeHtml((item.answer || "").slice(0, 180))}</div>
        <div class="button-row">
          <button class="button button-secondary button-small" type="button" data-feedback-to-case="${escapeHtml(item.id || "")}" ${hasCase ? "disabled" : ""}>加入回归</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderOverviewQuality(items = []) {
  const el = $("#overviewQualityList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("当前没有待处理质检记录。");
    return;
  }
  el.innerHTML = items.slice(0, 8).map((item) => `
    <div class="entity-card">
      <div class="entity-title-row">
        <h4 class="entity-title">${escapeHtml(item.message || "-")}</h4>
        ${statePill(statusLabel(item.status), statusType(item.status))}
      </div>
      <div class="entity-meta">${escapeHtml(item.error_reason || "待复核")} ｜ route: ${escapeHtml(item.route || "-")}</div>
    </div>
  `).join("");
}

function renderQualityRecordList(items = []) {
  const el = $("#qualityRecordList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无符合条件的质检记录。先在测试窗口或质量动作区记录一条反馈。");
    return;
  }
  el.innerHTML = items.map((item) => {
    const active = state.selectedQualityRecord?.id === item.id ? " active" : "";
    const riskType = item.need_human_review ? "warn" : (item.status === "resolved" ? "good" : answerFeedbackType(item.verdict));
    return `
      <button class="quality-record-card${active}" type="button" data-quality-record-id="${escapeHtml(item.id || "")}">
        <span class="quality-record-main">
          <strong>${escapeHtml(item.message || "-")}</strong>
          <small>${escapeHtml((item.answer || "").slice(0, 120))}</small>
        </span>
        <span class="quality-record-meta">
          ${statePill(item.need_human_review ? "待确认" : statusLabel(item.status), riskType)}
          <span>route: ${escapeHtml(item.route || "-")}</span>
          <span>${escapeHtml(item.error_reason || "无错误原因")}</span>
        </span>
      </button>
    `;
  }).join("");
}

function renderQualityDrawer(item) {
  const el = $("#qualityDetailDrawer");
  if (!el) return;
  if (!item) {
    el.innerHTML = `<div class="drawer-empty">选择一条问答记录查看详情。</div>`;
    return;
  }
  const sources = Array.isArray(item.sources || item.source) ? (item.sources || item.source) : [];
  el.innerHTML = `
    <div class="drawer-heading">
      <div>
        <p class="eyebrow">QA detail</p>
        <h3>${escapeHtml(item.message || "质检记录")}</h3>
      </div>
      ${statePill(item.need_human_review ? "需人工确认" : statusLabel(item.status), item.need_human_review ? "warn" : statusType(item.status))}
    </div>
    <div class="drawer-section">
      <h4>客户问题</h4>
      <div class="answer-box">${escapeHtml(item.message || "-")}</div>
    </div>
    <div class="drawer-section">
      <h4>AI 回答</h4>
      <div class="answer-box">${escapeHtml(item.answer || "-")}</div>
    </div>
    <div class="drawer-kv">
      <span>request_id</span><strong>${escapeHtml(item.request_id || "-")}</strong>
      <span>route</span><strong>${escapeHtml(item.route || "-")}</strong>
      <span>matched_rule</span><strong>${escapeHtml(item.matched_rule || "-")}</strong>
      <span>score</span><strong>${formatScore(item.score)}</strong>
      <span>need_human_review</span><strong>${item.need_human_review ? "是" : "否"}</strong>
      <span>status</span><strong>${escapeHtml(statusLabel(item.status))}</strong>
    </div>
    <div class="drawer-section">
      <h4>used_tools</h4>
      <div class="entity-tags">${tagList(item.used_tools || [], "未记录工具")}</div>
    </div>
    <div class="drawer-section">
      <h4>quality_flags</h4>
      <div class="entity-tags">${tagList(item.quality_flags || [], "无风险标记")}</div>
    </div>
    <div class="drawer-section">
      <h4>next_actions</h4>
      <div class="entity-tags">${tagList(item.next_actions || [], "暂无建议动作")}</div>
    </div>
    <div class="drawer-section">
      <h4>source</h4>
      <div class="stack-list">${renderSources(sources)}</div>
    </div>
    <div class="drawer-section">
      <h4>人工标注</h4>
      <div class="button-row">
        <button class="button button-secondary button-small" type="button" data-quality-annotation="correct">正确</button>
        <button class="button button-secondary button-small" type="button" data-quality-annotation="wrong">错误</button>
        <button class="button button-secondary button-small" type="button" data-quality-annotation="needs_optimization">需优化</button>
        <button class="button button-secondary button-small" type="button" data-quality-annotation="handoff">需转人工</button>
      </div>
    </div>
    <div class="drawer-section">
      <h4>修复动作</h4>
      <div class="fix-action-grid">
        <button class="button button-secondary button-small" type="button" data-quality-fix="add_faq">新增 FAQ</button>
        <button class="button button-secondary button-small" type="button" data-quality-fix="edit_knowledge">修改知识库</button>
        <button class="button button-secondary button-small" type="button" data-quality-fix="add_quote_rule">新增报价规则</button>
        <button class="button button-secondary button-small" type="button" data-quality-fix="add_regression_case">转回归测试</button>
        <button class="button button-primary button-small" type="button" data-quality-fix="resolved">标记已解决</button>
      </div>
    </div>
  `;
}

function statusLabel(status) {
  const map = {
    pending: "待处理",
    in_regression: "已入回归",
    resolved: "已修复",
    fixed: "已修复"
  };
  return map[status] || status || "待确认";
}

function statusType(status) {
  if (status === "resolved" || status === "fixed") return "good";
  if (status === "in_regression") return "warn";
  return "muted";
}

async function reloadQualityRecords() {
  const url = `${ADMIN_API}/quality-records${state.qualityFilter ? `?flag=${encodeURIComponent(state.qualityFilter)}` : ""}`;
  const data = await fetchJson(url);
  state.qualityRecords = data.items || [];
  if (state.selectedQualityRecord) {
    state.selectedQualityRecord = state.qualityRecords.find((item) => item.id === state.selectedQualityRecord.id) || null;
  }
  renderQualityRecordList(state.qualityRecords);
  renderQualityDrawer(state.selectedQualityRecord);
}

async function updateQualityRecord(recordId, payload) {
  const data = await fetchJson(`${ADMIN_API}/quality-records/${encodeURIComponent(recordId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  state.selectedQualityRecord = data.item || state.selectedQualityRecord;
  await reloadQualityRecords();
}

async function reloadQualityFeedback() {
  const data = await fetchJson(`${ADMIN_API}/answer-feedback`);
  state.answerFeedback = data.items || [];
  renderQualityFeedbackList(state.answerFeedback);
}

async function saveQualityFeedback(verdict, toRegression = false) {
  if (!state.lastQualityResult) {
    showNotice("qualityFeedbackNotice", "请先测试一个客户问题。", "error");
    return;
  }
  const snapshot = qualitySnapshot(state.lastQualityResult);
  const notes = $("#qualityFeedbackNotes")?.value || "";
  if (verdict === "style_issue" && !notes.trim()) {
    showNotice("qualityFeedbackNotice", "请先在备注里写清楚希望怎么改话术，例如更短、先给结论、少用内部词。", "error");
    return;
  }
  const payload = {
    message: snapshot.message,
    answer: snapshot.answer,
    verdict,
    notes,
    route: snapshot.route,
    expected_route: snapshot.route,
    expected_keywords: verdict === "good" ? compactKeywords(snapshot.answer) : [],
    forbidden_keywords: verdict === "good" ? [] : compactKeywords(snapshot.answer),
    snapshot
  };
  if (!payload.message) {
    showNotice("qualityFeedbackNotice", "问题为空，不能记录反馈。", "error");
    return;
  }
  showNotice("qualityFeedbackNotice", "正在记录反馈...", "loading");
  try {
    const data = await fetchJson(`${ADMIN_API}/answer-feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (toRegression) {
      await fetchJson(`${ADMIN_API}/answer-feedback/${encodeURIComponent(data.item.id)}/regression-case`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
    }
    if (verdict === "style_issue") {
      const draft = await fetchJson(`${ADMIN_API}/tuning/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction: [
            "优化客服回答话术。",
            `客户问题：${snapshot.message}`,
            `当前回答：${snapshot.answer}`,
            `希望调整：${notes}`,
            "请生成可审核的回答风格或行为规则草稿，不要直接改变事实口径。"
          ].join("\n")
        })
      });
      state.trainingDraft = draft.draft || null;
      showNotice("qualityFeedbackNotice", "已记录话术问题并生成训练草稿。请进入训练与测试页审核并应用后，下一次回答才会变化。", "success");
    } else {
      showNotice("qualityFeedbackNotice", toRegression ? "已记录反馈并加入回归测试。" : "已记录反馈。", "success");
    }
    await reloadQualityFeedback();
    await reloadQualityRecords();
  } catch (e) {
    showNotice("qualityFeedbackNotice", `记录失败：${e.message}`, "error");
  }
}

async function feedbackToRegressionCase(feedbackId) {
  if (!feedbackId) return;
  try {
    await fetchJson(`${ADMIN_API}/answer-feedback/${encodeURIComponent(feedbackId)}/regression-case`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    await reloadQualityFeedback();
  } catch (e) {
    showNotice("qualityFeedbackNotice", `加入回归失败：${e.message}`, "error");
  }
}

async function runQualityRegression() {
  const btn = $("#qualityRunRegressionBtn");
  const restore = setLoading(btn, "运行中...");
  $("#qualityRegressionSummary").textContent = "正在运行回归测试...";
  try {
    const data = await fetchJson(`${ADMIN_API}/regression-cases/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    $("#qualityRegressionSummary").innerHTML = `
      <strong>通过 ${data.passed || 0} / ${data.total || 0}</strong>
      <div class="entity-meta">失败 ${data.failed || 0} 条。${data.failed ? "请进入训练测试页查看细节。" : "当前测试集全部通过。"}</div>
    `;
  } catch (e) {
    $("#qualityRegressionSummary").innerHTML = `<div class="notice error">运行失败：${escapeHtml(e.message)}</div>`;
  } finally {
    restore();
  }
}

async function loadKnowledgePage() {
  const [summary, docs, faqs, rules, memories, learned, indexStatus] = await Promise.all([
    loadSummary(),
    fetchJson(`${ADMIN_API}/docs`),
    fetchJson(`${ADMIN_API}/faqs`),
    fetchJson(`${ADMIN_API}/rules`),
    fetchJson(`${ADMIN_API}/memories`),
    fetchJson(`${ADMIN_API}/learned-knowledge`),
    fetchJson(`${ADMIN_API}/knowledge-index-status`)
  ]);
  state.docs = docs.items || [];
  state.faqs = faqs.items || [];
  state.rules = rules.items || [];
  state.memories = memories.items || [];
  state.learnedKnowledge = learned.items || [];
  state.knowledgeIndexStatus = indexStatus;
  renderSummaryMetrics("knowledgeMetricGrid", summary);
  renderIndexStatus("knowledgeIndexStatus", indexStatus);
  renderDocsList(state.docs);
  renderFaqList(state.faqs);
  renderRulesList(state.rules);
  renderMemoryList(state.memories);
  renderLearnedList(state.learnedKnowledge);
  fillFaqForm(null);
  fillRuleForm(null);
  fillMemoryForm(null);
}

function renderIndexStatus(targetId, data) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!data) {
    el.innerHTML = emptyState("暂无索引状态。");
    return;
  }
  el.innerHTML = [
    statusCard("索引状态", data.pending_rebuild ? "待重建" : "已同步", data.pending_rebuild ? "warn" : "good", data.message || data.status || ""),
    statusCard("最后重建时间", data.last_rebuilt_at || "未记录", data.last_rebuilt_at ? "good" : "warn", `向量模型：${data.embed_model || "-"}`),
    statusCard("当前集合", data.current_collection || "-", "muted", `FAQ：${data.faq_collection || "-"} / 文档：${data.doc_collection || "-"}`),
    statusCard("Qdrant 集合", (data.collections || []).join("、") || "-", "muted", "知识检索实际使用的集合")
  ].join("");
}

function groupDocs(items) {
  const map = new Map();
  items.forEach((item) => {
    const name = item.doc_name || "未命名文档";
    const doc = map.get(name) || {
      name,
      source: item.source || "",
      category: item.category || "",
      method: item.extraction_method || "",
      type: item.doc_type || "",
      summary: item.summary || "",
      products: item.products || [],
      topics: item.topics || [],
      missingFields: item.missing_fields || [],
      diagnostics: item.analysis_diagnostics || {},
      updated_at: item.updated_at || "",
      items: []
    };
    doc.items.push(item);
    if (item.updated_at && item.updated_at > doc.updated_at) doc.updated_at = item.updated_at;
    if (!doc.summary && item.summary) doc.summary = item.summary;
    doc.products = Array.from(new Set([...(doc.products || []), ...((item.products || item.entities || []))]));
    doc.topics = Array.from(new Set([...(doc.topics || []), ...((item.topics || []))]));
    doc.missingFields = Array.from(new Set([...(doc.missingFields || []), ...((item.missing_fields || []))]));
    if (!doc.diagnostics?.text_char_count && item.analysis_diagnostics) doc.diagnostics = item.analysis_diagnostics;
    map.set(name, doc);
  });
  return Array.from(map.values());
}

const DOC_CHUNKS_PER_PAGE = 6;

function getDocPage(docName, totalItems) {
  const totalPages = Math.max(1, Math.ceil(totalItems / DOC_CHUNKS_PER_PAGE));
  const current = Number(state.docPages?.[docName] || 1);
  return Math.min(Math.max(1, current), totalPages);
}

function setDocPage(docName, page) {
  if (!docName) return;
  state.docPages = { ...(state.docPages || {}), [docName]: page };
  renderDocsList(state.docs);
}

function renderDocPager(doc, page, totalPages) {
  if (totalPages <= 1) return "";
  const start = (page - 1) * DOC_CHUNKS_PER_PAGE + 1;
  const end = Math.min(page * DOC_CHUNKS_PER_PAGE, doc.items.length);
  return `
    <div class="doc-pager" aria-label="${escapeHtml(doc.name)} 片段分页">
      <div class="doc-pager-info">显示 ${start}-${end} / ${doc.items.length} 个片段</div>
      <div class="doc-pager-controls">
        <button class="button button-secondary button-small" type="button" data-doc-page="${escapeHtml(doc.name)}" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>
        <span>${page} / ${totalPages}</span>
        <button class="button button-secondary button-small" type="button" data-doc-page="${escapeHtml(doc.name)}" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>下一页</button>
      </div>
    </div>
  `;
}

function renderDocsList(items) {
  const el = $("#knowledgeDocsList");
  if (!el) return;
  const docs = groupDocs(items);
  if (!docs.length) {
    el.innerHTML = emptyState("没有找到文档。");
    return;
  }
  el.innerHTML = docs.map((doc) => {
    const totalPages = Math.max(1, Math.ceil(doc.items.length / DOC_CHUNKS_PER_PAGE));
    const page = getDocPage(doc.name, doc.items.length);
    const startIndex = (page - 1) * DOC_CHUNKS_PER_PAGE;
    const visibleItems = doc.items.slice(startIndex, startIndex + DOC_CHUNKS_PER_PAGE);
    return `
    <details class="entity-card" open>
      <summary>
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(doc.name)}</h4>
          ${tag(`${doc.items.length} 个片段`)}
        </div>
        <div class="entity-meta">
          来源：${escapeHtml(doc.source || "-")} ｜ 分类：${escapeHtml(doc.category || "-")} ｜ 解析：${escapeHtml(doc.method || "-")}
        </div>
        <div class="entity-meta">
          摘要：${escapeHtml(doc.summary || "暂无摘要")} ｜ 产品：${tagList(doc.products)} ｜ 主题：${tagList(doc.topics)}
        </div>
        <div class="entity-meta">
          解析质量：${escapeHtml(doc.diagnostics?.text_char_count || "-")} 字 ｜ ${doc.items.length} 片段 ｜ 缺失字段：${tagList(doc.missingFields, "无")}
        </div>
        <div class="inline-actions">
          <button class="button button-danger button-small" type="button" data-doc-delete="${escapeHtml(doc.name)}">删除文档</button>
        </div>
      </summary>
      ${renderDocPager(doc, page, totalPages)}
      <div class="details-grid">
        ${visibleItems.map((item, index) => `
          <button class="detail-box doc-chunk-card" type="button" data-doc-chunk-id="${escapeHtml(item.id || "")}">
            <strong>片段 ${startIndex + index + 1} ｜ ${escapeHtml(item.section_title || item.section || "正文")}</strong>
            <div class="entity-meta">
              ${escapeHtml(item.page_range || "无页码")} ｜ 主题：${tagList(item.topics)} ｜ 实体：${tagList(item.entities || item.products)}
            </div>
            ${item.semantic_summary ? `<div class="entity-meta">语义摘要：${escapeHtml(item.semantic_summary)}</div>` : ""}
            <div>${escapeHtml(cleanDocDisplayText(item.text).slice(0, 260))}${cleanDocDisplayText(item.text).length > 260 ? "..." : ""}</div>
            <span class="text-link doc-chunk-open">查看详情</span>
          </button>
        `).join("")}
      </div>
      ${renderDocPager(doc, page, totalPages)}
    </details>
  `;
  }).join("");
}

function findDocChunk(chunkId) {
  for (const item of state.docs || []) {
    if (safeText(item.id) === safeText(chunkId)) return item;
  }
  return null;
}

function firstPageFromRange(value) {
  const match = safeText(value).match(/\d+/);
  return match ? Math.max(1, Number(match[0]) || 1) : 1;
}

function closeDocChunkModal() {
  state.docChunkModal = null;
  const modal = $("#docChunkModal");
  if (modal) modal.innerHTML = "";
}

function openDocChunkModal(chunkId) {
  const item = findDocChunk(chunkId);
  if (!item) return;
  state.docChunkModal = item;
  renderDocChunkModal(item);
}

function renderDocChunkModal(item) {
  let modal = $("#docChunkModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "docChunkModal";
    document.body.appendChild(modal);
  }
  const page = firstPageFromRange(item.page_range);
  const source = safeText(item.source).toLowerCase();
  const imageUrl = source.endsWith(".pdf")
    ? `${ADMIN_API}/docs/${encodeURIComponent(item.doc_name || "")}/page-image?page=${page}`
    : "";
  const readableText = humanTextBlock(item.text);
  const readableSummary = humanTextBlock(item.semantic_summary || item.summary, "这段还没有生成摘要。");
  modal.innerHTML = `
    <div class="doc-modal-backdrop" data-doc-modal-action="close">
      <section class="doc-modal-card" role="dialog" aria-modal="true" aria-label="文档片段详情">
        <header class="doc-modal-header">
          <div>
            <p class="eyebrow">文档片段</p>
            <h3>${escapeHtml(item.section_title || item.section || "片段详情")}</h3>
            <div class="entity-meta">
              文档：${escapeHtml(item.doc_name || "-")} ｜ 页码：${escapeHtml(item.page_range || `第${page}页`)} ｜ 来源：${escapeHtml(item.source || "-")}
            </div>
          </div>
          <button class="button button-secondary button-small" type="button" data-doc-modal-action="close">关闭</button>
        </header>
        <div class="doc-modal-body">
          <div class="doc-modal-content">
            <section class="doc-modal-section">
              <h4>这段文档讲什么</h4>
              <p>${readableText}</p>
            </section>
            <section class="doc-modal-section">
              <h4>AI 已识别的信息</h4>
              <div class="doc-meta-grid">
                <div><span>内容类型</span>${docTagList(item.topics, "未判断")}</div>
                <div><span>产品 / 型号 / 关键词</span>${docTagList(item.entities || item.products, "未识别到明确产品")}</div>
                <div><span>摘要</span><strong>${readableSummary}</strong></div>
                <div><span>价格信息</span>${formatDocValue(item.price_fields, "这段没有识别到价格字段")}</div>
                <div><span>报价原文</span>${formatDocValue(item.quote_items || item.price_items, "这段不是报价内容")}</div>
              </div>
            </section>
          </div>
          <aside class="doc-page-preview">
            <div class="doc-page-preview-head">
              <h4>原文页图</h4>
              <span class="entity-meta">第 ${escapeHtml(page)} 页</span>
            </div>
            ${imageUrl
              ? `<img src="${imageUrl}" alt="${escapeHtml(item.source || "文档")} 第 ${escapeHtml(page)} 页" loading="lazy" />`
              : `<div class="result-empty">当前文件不是 PDF，暂不支持页图预览。</div>`}
          </aside>
        </div>
      </section>
    </div>
  `;
}

async function uploadKnowledgeDocs(event) {
  event?.preventDefault();
  const input = $("#knowledgeDocFile");
  const files = Array.from(input?.files || []);
  if (!files.length) {
    showNotice("knowledgeDocNotice", "请先选择要上传的文件。", "error");
    return;
  }
  const form = new FormData();
  files.forEach((file) => form.append("file", file));
  form.append("doc_name", $("#knowledgeDocName")?.value.trim() || "");
  form.append("category", $("#knowledgeDocCategory")?.value.trim() || "");
  const restore = setLoading($("#knowledgeDocUploadBtn"), "上传中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/docs/upload`, { method: "POST", body: form });
    const analysis = (data.results || []).map((item) => item.analysis).find(Boolean) || data.analysis || {};
    const note = analysis.products?.length
      ? `识别产品：${analysis.products.slice(0, 5).join("、")}；价格项 ${analysis.price_item_count || 0}；缺失字段：${(analysis.missing_fields || []).join("、") || "无"}。`
      : "";
    showNotice("knowledgeDocNotice", `${data.message || "上传完成。"}${note ? " " + note : ""}`, data.ok ? "success" : "info");
    if (input) input.value = "";
    await loadKnowledgePage();
  } catch (e) {
    showNotice("knowledgeDocNotice", `上传失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function rebuildSemanticDocs() {
  const button = $("#knowledgeDocSemanticRebuildBtn");
  const restore = setLoading(button, "重建中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/docs/rebuild-semantic-index`, { method: "POST" });
    const suffix = data.index_error ? ` 向量入库失败：${data.index_error}` : "";
    showNotice("knowledgeDocNotice", `${data.message || "语义索引已重建。"}${suffix}`, data.ok ? "success" : "info");
    await loadKnowledgePage();
  } catch (e) {
    showNotice("knowledgeDocNotice", `重建失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function deleteKnowledgeDoc(docName) {
  if (!docName || !confirm(`确定删除文档“${docName}”及其所有片段吗？`)) return;
  try {
    await fetchJson(`${ADMIN_API}/docs/${encodeURIComponent(docName)}`, { method: "DELETE" });
    showNotice("knowledgeDocNotice", "文档已删除并重建文档索引。", "success");
    await loadKnowledgePage();
  } catch (e) {
    showNotice("knowledgeDocNotice", `删除失败：${e.message}`, "error");
  }
}

function renderFaqList(items) {
  const el = $("#knowledgeFaqList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无 FAQ。");
    return;
  }
  el.innerHTML = items.slice(0, 80).map((item) => {
    const questions = Array.isArray(item.questions) ? item.questions : [];
    return `
      <details class="entity-card">
        <summary>
          <div class="entity-title-row">
            <h4 class="entity-title">${escapeHtml(questions[0] || item.id || "FAQ")}</h4>
            ${statePill(item.status === "active" ? "已启用" : "未启用", item.status === "active" ? "good" : "bad")}
          </div>
          <div class="entity-meta">分类：${escapeHtml(item.category || "-")} ｜ 优先级 ${escapeHtml(item.priority || 1)} ｜ 问法 ${questions.length}</div>
        </summary>
        <div class="entity-body">${escapeHtml(item.answer || "")}</div>
        <div class="entity-tags">${(item.tags || []).map(tag).join("")}</div>
        <div class="button-row">
          <button class="button button-secondary button-small" type="button" data-faq-edit="${escapeHtml(item.id || "")}">编辑</button>
        </div>
      </details>
    `;
  }).join("");
}

function fillFaqForm(item) {
  state.selectedFaq = item || null;
  $("#knowledgeFaqId").value = item?.id || "";
  $("#knowledgeFaqStatus").value = item?.status || "active";
  $("#knowledgeFaqPriority").value = item?.priority || 1;
  $("#knowledgeFaqCategory").value = item?.category || "";
  $("#knowledgeFaqSource").value = item?.source || "";
  $("#knowledgeFaqQuestions").value = (item?.questions || []).join("\n");
  $("#knowledgeFaqAnswer").value = item?.answer || "";
  $("#knowledgeFaqTags").value = (item?.tags || []).join("、");
  hideNotice("knowledgeFaqNotice");
}

function collectFaqForm(forceNew = false) {
  const id = forceNew ? "" : ($("#knowledgeFaqId")?.value || "");
  return {
    id: id || null,
    status: $("#knowledgeFaqStatus")?.value || "active",
    priority: Number($("#knowledgeFaqPriority")?.value || 1),
    category: $("#knowledgeFaqCategory")?.value.trim() || "",
    source: $("#knowledgeFaqSource")?.value.trim() || "",
    questions: splitWords($("#knowledgeFaqQuestions")?.value || ""),
    answer: $("#knowledgeFaqAnswer")?.value.trim() || "",
    tags: splitWords($("#knowledgeFaqTags")?.value || "")
  };
}

async function saveKnowledgeFaq(event, forceNew = false) {
  event?.preventDefault();
  const payload = collectFaqForm(forceNew);
  const id = payload.id;
  const restore = setLoading($("#knowledgeFaqSaveBtn"), "保存中...");
  try {
    const data = await fetchJson(id ? `${ADMIN_API}/faqs/${encodeURIComponent(id)}` : `${ADMIN_API}/faqs`, {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    showNotice("knowledgeFaqNotice", "FAQ 已保存，FAQ 向量索引已重建。", "success");
    await refreshKnowledgeFaqs();
    fillFaqForm(data.item || null);
  } catch (e) {
    showNotice("knowledgeFaqNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function deleteKnowledgeFaq() {
  const id = $("#knowledgeFaqId")?.value || "";
  if (!id) {
    showNotice("knowledgeFaqNotice", "请先选择要删除的 FAQ。", "error");
    return;
  }
  if (!confirm(`确定删除 FAQ ${id} 吗？`)) return;
  try {
    await fetchJson(`${ADMIN_API}/faqs/${encodeURIComponent(id)}`, { method: "DELETE" });
    showNotice("knowledgeFaqNotice", "FAQ 已删除，FAQ 向量索引已重建。", "success");
    await refreshKnowledgeFaqs();
    fillFaqForm(null);
  } catch (e) {
    showNotice("knowledgeFaqNotice", `删除失败：${e.message}`, "error");
  }
}

async function refreshKnowledgeFaqs(q = "") {
  const data = await fetchJson(`${ADMIN_API}/faqs${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  state.faqs = data.items || [];
  renderFaqList(state.faqs);
}

async function reindexKnowledgeFaqs() {
  const restore = setLoading($("#knowledgeFaqReindexBtn"), "重建中...");
  try {
    await fetchJson(`${ADMIN_API}/faqs/reindex`, { method: "POST" });
    showNotice("knowledgeFaqNotice", "FAQ 索引已重建。", "success");
  } catch (e) {
    showNotice("knowledgeFaqNotice", `重建失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

function ruleActionText(action) {
  const map = {
    faq_first: "优先 FAQ",
    manual_required: "必须转人工",
    doc_first: "优先文档",
    block_commitment: "禁止承诺"
  };
  return map[action] || action || "-";
}

function renderRulesList(items) {
  const el = $("#knowledgeRuleList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无优先规则。");
    return;
  }
  el.innerHTML = items.slice(0, 80).map((item) => `
    <details class="entity-card">
      <summary>
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.rule_name || item.id || "规则")}</h4>
          ${statePill(ruleActionText(item.action), item.action === "manual_required" || item.action === "block_commitment" ? "warn" : "good")}
        </div>
        <div class="entity-meta">分类：${escapeHtml(item.category || "-")} ｜ 状态：${escapeHtml(item.status || "-")} ｜ 优先级 ${escapeHtml(item.priority || 1)}</div>
      </summary>
      <div class="entity-tags">${(item.keywords || []).map(tag).join("")}</div>
      <div class="entity-body">${escapeHtml(item.note || "")}</div>
      <div class="button-row">
        <button class="button button-secondary button-small" type="button" data-rule-edit="${escapeHtml(item.id || "")}">编辑</button>
      </div>
    </details>
  `).join("");
}

function fillRuleForm(item) {
  state.selectedRule = item || null;
  $("#knowledgeRuleId").value = item?.id || "";
  $("#knowledgeRuleName").value = item?.rule_name || "";
  $("#knowledgeRuleAction").value = item?.action || "faq_first";
  $("#knowledgeRuleStatus").value = item?.status || "active";
  $("#knowledgeRulePriority").value = item?.priority || 1;
  $("#knowledgeRuleCategory").value = item?.category || "";
  $("#knowledgeRuleKeywords").value = (item?.keywords || []).join("\n");
  $("#knowledgeRuleNote").value = item?.note || "";
  hideNotice("knowledgeRuleNotice");
}

function collectRuleForm(forceNew = false) {
  const id = forceNew ? "" : ($("#knowledgeRuleId")?.value || "");
  return {
    id: id || null,
    rule_name: $("#knowledgeRuleName")?.value.trim() || "",
    action: $("#knowledgeRuleAction")?.value || "faq_first",
    status: $("#knowledgeRuleStatus")?.value || "active",
    priority: Number($("#knowledgeRulePriority")?.value || 1),
    category: $("#knowledgeRuleCategory")?.value.trim() || "",
    keywords: splitWords($("#knowledgeRuleKeywords")?.value || ""),
    note: $("#knowledgeRuleNote")?.value.trim() || ""
  };
}

async function saveKnowledgeRule(event, forceNew = false) {
  event?.preventDefault();
  const payload = collectRuleForm(forceNew);
  const id = payload.id;
  const restore = setLoading($("#knowledgeRuleSaveBtn"), "保存中...");
  try {
    const data = await fetchJson(id ? `${ADMIN_API}/rules/${encodeURIComponent(id)}` : `${ADMIN_API}/rules`, {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    showNotice("knowledgeRuleNotice", "规则已保存。", "success");
    await refreshKnowledgeRules();
    fillRuleForm(data.item || null);
  } catch (e) {
    showNotice("knowledgeRuleNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function deleteKnowledgeRule() {
  const id = $("#knowledgeRuleId")?.value || "";
  if (!id) {
    showNotice("knowledgeRuleNotice", "请先选择要删除的规则。", "error");
    return;
  }
  if (!confirm(`确定删除规则 ${id} 吗？`)) return;
  try {
    await fetchJson(`${ADMIN_API}/rules/${encodeURIComponent(id)}`, { method: "DELETE" });
    showNotice("knowledgeRuleNotice", "规则已删除。", "success");
    await refreshKnowledgeRules();
    fillRuleForm(null);
  } catch (e) {
    showNotice("knowledgeRuleNotice", `删除失败：${e.message}`, "error");
  }
}

async function refreshKnowledgeRules(q = "") {
  const data = await fetchJson(`${ADMIN_API}/rules${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  state.rules = data.items || [];
  renderRulesList(state.rules);
}

async function testKnowledgeRule() {
  const text = $("#knowledgeRuleTestInput")?.value.trim() || "";
  if (!text) {
    showNotice("knowledgeRuleNotice", "请输入要测试的客户问题。", "error");
    return;
  }
  try {
    const data = await fetchJson(`${ADMIN_API}/rules/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const rule = data.rule || {};
    showNotice("knowledgeRuleNotice", data.matched ? `命中规则：${rule.rule_name || rule.id || "-"}，关键词：${rule.matched_keyword || "-"}` : "未命中任何启用规则。", data.matched ? "success" : "info");
  } catch (e) {
    showNotice("knowledgeRuleNotice", `测试失败：${e.message}`, "error");
  }
}

function renderLearnedList(items) {
  const el = $("#knowledgeLearnedList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无纠错学习内容。");
    return;
  }
  el.innerHTML = items.slice(0, 80).map((item) => `
    <details class="entity-card">
      <summary>
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.category || "学习知识")}</h4>
          ${tag(item.channel || "api")}
        </div>
        <div class="entity-meta">客户：${escapeHtml(item.user_id || "-")} ｜ 更新时间：${escapeHtml(item.updated_at || item.created_at || "-")}</div>
      </summary>
      <div class="entity-body">${escapeHtml(item.corrected_fact || "")}</div>
      <div class="entity-meta">线索：${escapeHtml(item.question_hint || "-")}</div>
      <div class="button-row">
        <button class="button button-danger button-small" type="button" data-learned-delete="${escapeHtml(item.id || item.learned_id || "")}">删除</button>
      </div>
    </details>
  `).join("");
}

function renderMemoryList(items, targetId = "knowledgeMemoryList") {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无客户记忆。填写客户 ID 的聊天会自动生成，也可以在这里手动维护。");
    return;
  }
  el.innerHTML = items.slice(0, 80).map((item) => `
    <details class="entity-card">
      <summary>
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.customer_name || item.user_id || "客户记忆")}</h4>
          ${tag(item.channel || "api")}
        </div>
        <div class="entity-meta">客户 ID：${escapeHtml(item.user_id || "-")} ｜ 场景：${escapeHtml(item.scenario || "-")} ｜ 预算：${escapeHtml(item.budget || "-")}</div>
      </summary>
      <div class="entity-tags">${(item.products || []).map(tag).join("")}${(item.risk_flags || []).map((value) => statePill(value, "warn")).join("")}</div>
      <div class="entity-body">${escapeHtml(item.notes || "暂无备注")}</div>
      <div class="button-row">
        <button class="button button-secondary button-small" type="button" data-memory-edit="${escapeHtml(item.channel || "api")}:${escapeHtml(item.user_id || "")}">编辑</button>
      </div>
    </details>
  `).join("");
}

function fillMemoryForm(item) {
  state.selectedMemory = item || null;
  $("#knowledgeMemoryChannel").value = item?.channel || "api";
  $("#knowledgeMemoryUserId").value = item?.user_id || "";
  $("#knowledgeMemoryName").value = item?.customer_name || "";
  $("#knowledgeMemoryContact").value = item?.contact || "";
  $("#knowledgeMemoryScenario").value = item?.scenario || "";
  $("#knowledgeMemoryBudget").value = item?.budget || "";
  $("#knowledgeMemoryNotes").value = item?.notes || "";
  $("#knowledgeMemoryLists").value = [
    `产品=${(item?.products || []).join("、")}`,
    `偏好=${(item?.preferences || []).join("、")}`,
    `风险=${(item?.risk_flags || []).join("、")}`,
    `关注=${(item?.concerns || []).join("、")}`,
    `历史报价=${(item?.quoted_schemes || []).join("、")}`,
    `常问=${(item?.common_questions || []).join("、")}`,
  ].join("\n");
  hideNotice("knowledgeMemoryNotice");
}

function parseMemoryLists(raw) {
  const result = {
    products: [],
    preferences: [],
    risk_flags: [],
    concerns: [],
    quoted_schemes: [],
    common_questions: []
  };
  const keyMap = {
    "产品": "products",
    "偏好": "preferences",
    "风险": "risk_flags",
    "关注": "concerns",
    "关注点": "concerns",
    "历史报价": "quoted_schemes",
    "报价": "quoted_schemes",
    "常问": "common_questions"
  };
  safeText(raw).split(/\n+/).forEach((line) => {
    const [keyRaw, ...rest] = line.split(/[=:：]/);
    const field = keyMap[(keyRaw || "").trim()];
    if (!field) return;
    result[field] = splitWords(rest.join("=").trim());
  });
  return result;
}

function collectMemoryForm() {
  return {
    channel: $("#knowledgeMemoryChannel")?.value || "api",
    user_id: $("#knowledgeMemoryUserId")?.value.trim() || "",
    customer_name: $("#knowledgeMemoryName")?.value.trim() || "",
    contact: $("#knowledgeMemoryContact")?.value.trim() || "",
    scenario: $("#knowledgeMemoryScenario")?.value.trim() || "",
    budget: $("#knowledgeMemoryBudget")?.value.trim() || "",
    project_time: state.selectedMemory?.project_time || "",
    decision_status: state.selectedMemory?.decision_status || "",
    notes: $("#knowledgeMemoryNotes")?.value.trim() || "",
    ...parseMemoryLists($("#knowledgeMemoryLists")?.value || "")
  };
}

async function saveKnowledgeMemory(event) {
  event?.preventDefault();
  const payload = collectMemoryForm();
  if (!payload.user_id) {
    showNotice("knowledgeMemoryNotice", "客户 ID 不能为空。", "error");
    return;
  }
  const restore = setLoading($("#knowledgeMemorySaveBtn"), "保存中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/memories/${encodeURIComponent(payload.channel)}/${encodeURIComponent(payload.user_id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    showNotice("knowledgeMemoryNotice", "客户记忆已保存。", "success");
    await refreshKnowledgeMemories();
    fillMemoryForm(data.item || payload);
  } catch (e) {
    showNotice("knowledgeMemoryNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function deleteKnowledgeMemory() {
  const channel = $("#knowledgeMemoryChannel")?.value || "api";
  const userId = $("#knowledgeMemoryUserId")?.value.trim() || "";
  if (!userId) {
    showNotice("knowledgeMemoryNotice", "请先选择要删除的客户记忆。", "error");
    return;
  }
  if (!confirm(`确定删除 ${channel}:${userId} 的客户记忆吗？`)) return;
  try {
    await fetchJson(`${ADMIN_API}/memories/${encodeURIComponent(channel)}/${encodeURIComponent(userId)}`, { method: "DELETE" });
    showNotice("knowledgeMemoryNotice", "客户记忆已删除。", "success");
    await refreshKnowledgeMemories();
    fillMemoryForm(null);
  } catch (e) {
    showNotice("knowledgeMemoryNotice", `删除失败：${e.message}`, "error");
  }
}

async function refreshKnowledgeMemories(q = "") {
  const data = await fetchJson(`${ADMIN_API}/memories${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  state.memories = data.items || [];
  renderMemoryList(state.memories);
}

async function deleteLearnedKnowledge(id) {
  if (!id || !confirm(`确定删除学习项 ${id} 并重建学习索引吗？`)) return;
  try {
    await fetchJson(`${ADMIN_API}/learned-knowledge/${encodeURIComponent(id)}`, { method: "DELETE" });
    showNotice("knowledgeLearnedNotice", "学习项已删除并重建索引。", "success");
    await refreshLearnedKnowledge();
  } catch (e) {
    showNotice("knowledgeLearnedNotice", `删除失败：${e.message}`, "error");
  }
}

async function refreshLearnedKnowledge(q = "") {
  const data = await fetchJson(`${ADMIN_API}/learned-knowledge${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  state.learnedKnowledge = data.items || [];
  renderLearnedList(state.learnedKnowledge);
}

async function reindexLearnedKnowledge() {
  const restore = setLoading($("#knowledgeLearnedReindexBtn"), "重建中...");
  try {
    await fetchJson(`${ADMIN_API}/learned-knowledge/reindex`, { method: "POST" });
    showNotice("knowledgeLearnedNotice", "学习库索引已重建。", "success");
  } catch (e) {
    showNotice("knowledgeLearnedNotice", `重建失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function searchKnowledgeDocs() {
  const q = $("#knowledgeDocSearch")?.value.trim() || "";
  const data = await fetchJson(`${ADMIN_API}/docs?q=${encodeURIComponent(q)}`);
  state.docs = data.items || [];
  renderDocsList(data.items || []);
}

async function searchLearnedKnowledge() {
  const q = $("#knowledgeLearnedSearch")?.value.trim() || "";
  await refreshLearnedKnowledge(q);
}

async function searchKnowledgeMemories() {
  const q = $("#knowledgeMemorySearch")?.value.trim() || "";
  await refreshKnowledgeMemories(q);
}

async function loadSalesPage() {
  const [policy, catalog, archives] = await Promise.all([
    fetchJson(`${ADMIN_API}/quote-policies`),
    fetchJson(`${ADMIN_API}/quote-catalog`),
    fetchJson(`${ADMIN_API}/quote-archives`)
  ]);
  state.quotePolicy = policy || {};
  state.quoteCatalog = normalizeQuoteCatalog(catalog);
  renderSalesPolicyForm(state.quotePolicy);
  renderQuoteCatalog(state.quoteCatalog);
  renderQuoteArchives(archives.items || [], archives.total || 0);
}

function configNeedLabel(key) {
  const labels = {
    scenario: "场景",
    budget: "预算",
    budget_value: "预算数字",
    track_length: "轨道长度",
    camera_count: "相机位",
    camera_payload: "承载重量",
    tracking_required: "跟踪",
    freed_required: "FreeD/XR",
    focus_required: "FIZ/焦点",
    dmx_required: "灯光/DMX",
    keyboard_required: "控制键盘",
    training_required: "培训",
    delivery_urgency: "交付时间",
    explicit_products: "客户点名产品"
  };
  return labels[key] || key;
}

function renderConfigNeeds(needs = {}) {
  const hiddenKeys = new Set(["raw_message", "budget_value"]);
  const entries = Object.entries(needs).filter(([key, value]) => {
    if (hiddenKeys.has(key)) return false;
    if (Array.isArray(value)) return value.length;
    return value !== null && value !== undefined && value !== "" && value !== false;
  });
  if (!entries.length) return emptyState("还没有识别出明确需求变量。");
  return `<div class="config-chip-grid">${entries.map(([key, value]) => {
    const text = Array.isArray(value) ? value.join("、") : value === true ? "是" : safeText(value);
    return `<div class="config-chip"><span>${escapeHtml(configNeedLabel(key))}</span><strong>${escapeHtml(text)}</strong></div>`;
  }).join("")}</div>`;
}

function renderConfigModules(modules = []) {
  if (!modules.length) return emptyState("暂未匹配到推荐模块。");
  return `<div class="config-module-grid">${modules.map((item) => `
    <div class="config-module-card">
      <div class="entity-title-row">
        <strong>${escapeHtml(item.name || item.id || "-")}</strong>
        ${statePill(item.role === "required" ? "必选" : "可选", item.role === "required" ? "good" : "muted")}
      </div>
      <div class="entity-meta">${escapeHtml(item.reason || "按场景规则推荐")}</div>
      ${item.reference_price ? `<div class="config-price">${escapeHtml(item.reference_price)}</div>` : ""}
    </div>
  `).join("")}</div>`;
}

function renderConfigQuoteItems(items = []) {
  if (!items.length) return emptyState("暂无报价明细。");
  return `
    <div class="table-wrap">
      <table class="table-lite config-quote-table">
        <thead>
          <tr><th>项目</th><th>数量</th><th>参考单价</th><th>小计</th><th>说明</th></tr>
        </thead>
        <tbody>
          ${items.map((item) => `
            <tr>
              <td><strong>${escapeHtml(item.name || item.id || "-")}</strong></td>
              <td>${escapeHtml(item.quantity ?? 1)} ${escapeHtml(item.unit || "")}</td>
              <td>${escapeHtml(item.reference_price || formatMoney(item.unit_price))}</td>
              <td>${escapeHtml(item.reference_total || formatMoney(item.total_price))}</td>
              <td>${escapeHtml(item.note || item.reason || "")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderConfigList(items = [], fallback) {
  if (!items.length) return emptyState(fallback);
  return `<ul class="config-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderConfigSources(items = []) {
  if (!items.length) return emptyState("本次没有匹配到资料来源。");
  return `<div class="config-source-list">${items.slice(0, 6).map((item) => `
    <div class="source-card">
      <div class="entity-title-row">
        <strong>${escapeHtml(item.title || item.doc_name || item.source || "来源")}</strong>
        ${tag(item.type || "source")}
      </div>
      <div class="entity-meta">${escapeHtml(item.section || item.category || "")}${item.snippet ? ` ｜ ${escapeHtml(item.snippet)}` : ""}</div>
    </div>
  `).join("")}</div>`;
}

function renderConfigQuoteDraft(data) {
  state.configQuoteDraft = data;
  const el = $("#configQuoteResult");
  if (!el) return;
  const type = data.status === "ready_for_review" ? "warn" : "muted";
  el.innerHTML = `
    <div class="config-summary">
      <div>
        <div class="entity-meta">拆解摘要</div>
        <h4>${escapeHtml(data.summary || "已生成配置报价草稿")}</h4>
      </div>
      ${statePill(data.status === "ready_for_review" ? "待销售复核" : "草稿", type)}
    </div>
    <div class="config-result-grid">
      <section>
        <h4>需求变量</h4>
        ${renderConfigNeeds(data.needs || {})}
      </section>
      <section>
        <h4>模块建议</h4>
        ${renderConfigModules(data.modules || [])}
      </section>
    </div>
    <section>
      <h4>报价明细草稿</h4>
      ${renderConfigQuoteItems(data.quote_items || [])}
    </section>
    <div class="config-result-grid">
      <section>
        <h4>需要确认</h4>
        ${renderConfigList(data.missing_questions || [], "暂时没有缺口问题。")}
      </section>
      <section>
        <h4>复核提醒</h4>
        ${renderConfigList(data.review_flags || [], "暂无明显风险。")}
      </section>
    </div>
    <section>
      <h4>参考来源</h4>
      ${renderConfigSources(data.source_refs || [])}
    </section>
    <div class="feedback-bar">
      <button class="button button-secondary button-small" type="button" data-config-feedback="usable">标记可用</button>
      <button class="button button-secondary button-small" type="button" data-config-feedback="needs_change">需要调整</button>
      <button class="button button-secondary button-small" type="button" data-config-feedback="missing_item">缺少项目</button>
    </div>
  `;
}

async function draftConfigQuote(event) {
  event?.preventDefault();
  const message = $("#configQuoteInput")?.value.trim() || "";
  if (!message) {
    $("#configQuoteResult").innerHTML = `<div class="notice error">请先输入客户需求描述。</div>`;
    return;
  }
  const btn = $("#configQuoteDraftBtn");
  const restore = setLoading(btn, "生成中...");
  $("#configQuoteResult").innerHTML = `<div class="notice loading">正在拆解场景、匹配价目和生成待确认项...</div>`;
  try {
    const data = await fetchJson(`${ADMIN_API}/config-quotes/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        scenario: $("#configQuoteScenario")?.value || "live_commerce",
        metadata: { source: "admin_sales_workbench" }
      })
    });
    renderConfigQuoteDraft(data);
  } catch (e) {
    $("#configQuoteResult").innerHTML = `<div class="notice error">生成失败：${escapeHtml(e.message)}</div>`;
  } finally {
    restore();
  }
}

async function saveConfigQuoteFeedback(verdict) {
  if (!state.configQuoteDraft) return;
  const noteMap = {
    usable: "销售标记草稿可用",
    needs_change: "销售标记草稿需要调整",
    missing_item: "销售标记草稿缺少项目"
  };
  try {
    await fetchJson(`${ADMIN_API}/config-quotes/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: $("#configQuoteInput")?.value.trim() || "",
        verdict,
        notes: noteMap[verdict] || "",
        draft: state.configQuoteDraft
      })
    });
    const bar = $(".feedback-bar");
    if (bar) bar.insertAdjacentHTML("beforeend", `<span class="state-pill state-good">已记录</span>`);
  } catch (e) {
    const bar = $(".feedback-bar");
    if (bar) bar.insertAdjacentHTML("beforeend", `<span class="state-pill state-bad">记录失败</span>`);
  }
}

function renderSalesPolicyForm(policy) {
  const approval = new Set(Array.isArray(policy.approval_required) ? policy.approval_required : []);
  const options = ["优惠价", "低于标价", "交付时间", "合同条款", "特殊定制"];
  $("#salesPolicyForm").innerHTML = `
    <label class="field">
      <span>报价模式</span>
      <select id="salesPolicyMode"><option value="draft_only">报价草案</option></select>
    </label>
    <label class="field">
      <span>未配置规则时</span>
      <select id="salesPolicyDefault">
        <option value="list_price_only">只报标价</option>
        <option value="no_amount">不出金额</option>
      </select>
    </label>
    <label class="field">
      <span>最大折扣比例</span>
      <input id="salesPolicyDiscount" type="number" min="0" max="100" step="0.1" value="${escapeHtml(policy.max_discount_percent ?? "")}" />
    </label>
    <label class="field">
      <span>回复风格</span>
      <select id="salesPolicyReplyStyle">
        <option value="sales_talk">销售话术</option>
        <option value="scheme_first">方案优先</option>
        <option value="table_like">清单式</option>
      </select>
    </label>
    <label class="field field-wide">
      <span>最低毛利/底价说明</span>
      <input id="salesPolicyMargin" type="text" value="${escapeHtml(policy.min_margin_note || "")}" />
    </label>
    <div class="field field-wide">
      <span>需人工确认项</span>
      <div class="entity-tags">
        ${options.map((item) => `
          <label class="tag"><input type="checkbox" class="sales-approval-check" value="${escapeHtml(item)}" ${approval.has(item) ? "checked" : ""} /> ${escapeHtml(item)}</label>
        `).join("")}
      </div>
    </div>
    <label class="field field-wide">
      <span>话术模板</span>
      <textarea id="salesPolicyTemplate" rows="5">${escapeHtml(policy.template || "")}</textarea>
    </label>
  `;
  $("#salesPolicyMode").value = policy.mode || "draft_only";
  $("#salesPolicyDefault").value = policy.default_when_unconfigured || "list_price_only";
  $("#salesPolicyReplyStyle").value = policy.reply_style || "sales_talk";
}

function collectSalesPolicyForm() {
  const discountRaw = $("#salesPolicyDiscount")?.value || "";
  const discount = discountRaw === "" ? "" : Number(discountRaw);
  return {
    mode: $("#salesPolicyMode")?.value || "draft_only",
    default_when_unconfigured: $("#salesPolicyDefault")?.value || "list_price_only",
    max_discount_percent: Number.isFinite(discount) ? discount : "",
    min_margin_note: $("#salesPolicyMargin")?.value.trim() || "",
    approval_required: $all(".sales-approval-check:checked").map((input) => input.value),
    reply_style: $("#salesPolicyReplyStyle")?.value || "sales_talk",
    template: $("#salesPolicyTemplate")?.value.trim() || ""
  };
}

function syncQuoteCatalogJson() {
  const json = $("#salesCatalogJson");
  if (json) json.value = JSON.stringify(state.quoteCatalog, null, 2);
}

function refreshCatalogInspector() {
  const inspector = $("#salesCatalogInspector");
  if (inspector) inspector.innerHTML = renderCatalogInspector(state.quoteCatalog, getSelectedPackage());
  syncQuoteCatalogJson();
}

function setQuoteCatalogDirty(message = "规则库已修改，点击“保存规则库”后聊天报价才会使用。") {
  refreshCatalogInspector();
  showNotice("salesCatalogNotice", message, "info");
}

function getSelectedPackage(catalog = state.quoteCatalog) {
  const packages = catalog.packages || [];
  if (!packages.length) return null;
  const selected = packages.find((item) => item.id === state.selectedQuotePackageId);
  return selected || packages[0];
}

function optionMembership(optionId, pkg) {
  if (!pkg) return "";
  const required = new Set(pkg.required_options || []);
  const recommended = new Set(pkg.recommended_options || []);
  if (required.has(optionId)) return "必选";
  if (recommended.has(optionId)) return "推荐";
  return "";
}

function updatePackageOptionMembership(pkg, optionId, bucket, checked) {
  const required = new Set(pkg.required_options || []);
  const recommended = new Set(pkg.recommended_options || []);
  if (bucket === "required") {
    checked ? required.add(optionId) : required.delete(optionId);
    if (checked) recommended.delete(optionId);
  } else {
    checked ? recommended.add(optionId) : recommended.delete(optionId);
    if (checked) required.delete(optionId);
  }
  pkg.required_options = Array.from(required);
  pkg.recommended_options = Array.from(recommended);
}

function removeOptionEverywhere(optionId) {
  (state.quoteCatalog.packages || []).forEach((pkg) => {
    pkg.required_options = (pkg.required_options || []).filter((id) => id !== optionId);
    pkg.recommended_options = (pkg.recommended_options || []).filter((id) => id !== optionId);
  });
}

function optionEditorRows(options, pkg) {
  if (!options.length) return emptyState("暂无选配，先在下方新增。");
  const required = new Set(pkg.required_options || []);
  const recommended = new Set(pkg.recommended_options || []);
  return `
    <div class="package-option-editor">
      ${options.map((option) => `
        <div class="package-option-row">
          <div>
            <strong>${escapeHtml(option.name || option.id || "-")}</strong>
            <small>${escapeHtml(option.id || "-")} ｜ ${escapeHtml(option.reference_price || "未标价")}</small>
          </div>
          <label class="mini-check">
            <input type="checkbox" data-catalog-action="package-option" data-package-id="${escapeHtml(pkg.id || "")}" data-option-id="${escapeHtml(option.id || "")}" data-bucket="required" ${required.has(option.id) ? "checked" : ""} />
            必选
          </label>
          <label class="mini-check">
            <input type="checkbox" data-catalog-action="package-option" data-package-id="${escapeHtml(pkg.id || "")}" data-option-id="${escapeHtml(option.id || "")}" data-bucket="recommended" ${recommended.has(option.id) ? "checked" : ""} />
            推荐
          </label>
        </div>
      `).join("")}
    </div>
  `;
}

function renderCatalogEditorCard(catalog, selectedPackage, armOptions, priceVersions) {
  const editor = state.catalogEditor;
  if (!editor) return "";
  if (editor.type === "package") {
    const item = findCatalogPackage(editor.id) || selectedPackage;
    if (!item) return "";
    return `
      <section class="catalog-editor-card">
        <div class="catalog-editor-head">
          <div>
            <p class="eyebrow">Package editor</p>
            <h4>编辑版本包：${escapeHtml(item.name || item.id || "-")}</h4>
            <p>在这里调整版本包基础信息和包含配件，外层卡片只保留预览。</p>
          </div>
          <button class="button button-secondary button-small" type="button" data-catalog-action="close-editor">收起编辑</button>
        </div>
        <div class="catalog-editor-body">
          <div class="form-grid form-grid-compact">
            <label class="field">
              <span>版本包名称</span>
              <input data-catalog-action="package-field" data-package-id="${escapeHtml(item.id || "")}" data-field="name" value="${escapeHtml(item.name || "")}" />
            </label>
            <label class="field">
              <span>适用场景</span>
              <input data-catalog-action="package-field" data-package-id="${escapeHtml(item.id || "")}" data-field="scenario" value="${escapeHtml(item.scenario || "")}" />
            </label>
            <label class="field">
              <span>默认臂型</span>
              <select data-catalog-action="package-field" data-package-id="${escapeHtml(item.id || "")}" data-field="default_arm">
                ${armOptions}
              </select>
            </label>
            <label class="field">
              <span>价格版本</span>
              <select data-catalog-action="package-field" data-package-id="${escapeHtml(item.id || "")}" data-field="price_version">
                ${priceVersions.map((version) => `<option value="${escapeHtml(version)}">${escapeHtml(version)}</option>`).join("")}
              </select>
            </label>
            <label class="field field-wide">
              <span>备选臂型（用逗号或顿号分隔）</span>
              <input data-catalog-action="package-list-field" data-package-id="${escapeHtml(item.id || "")}" data-field="alternative_arms" value="${escapeHtml(joinWords(item.alternative_arms || []))}" />
            </label>
            <label class="field field-wide">
              <span>版本说明</span>
              <textarea data-catalog-action="package-field" data-package-id="${escapeHtml(item.id || "")}" data-field="description" rows="3">${escapeHtml(item.description || "")}</textarea>
            </label>
          </div>
          <div class="catalog-editor-title">版本包配件选择</div>
          ${optionEditorRows(catalog.options || [], item)}
        </div>
      </section>
    `;
  }
  if (editor.type === "arm") {
    const item = findCatalogArm(editor.id);
    if (!item) return "";
    const prices = Object.entries(item.prices || {});
    return `
      <section class="catalog-editor-card">
        <div class="catalog-editor-head">
          <div>
            <p class="eyebrow">Arm price editor</p>
            <h4>编辑机械臂价格：${escapeHtml(item.name || item.id || "-")}</h4>
            <p>每个版本价格可以单独调整，也可以新增或删除价格版本。</p>
          </div>
          <button class="button button-secondary button-small" type="button" data-catalog-action="close-editor">收起编辑</button>
        </div>
        <div class="catalog-editor-body">
          <div class="arm-price-editor editor-price-list">
            ${prices.length ? prices.map(([key, value]) => `
              <label class="price-row">
                <span>${escapeHtml(key)}</span>
                <input data-catalog-action="arm-price" data-arm-id="${escapeHtml(item.id || "")}" data-price-key="${escapeHtml(key)}" value="${escapeHtml(value)}" />
                <button class="button button-secondary button-mini" type="button" data-catalog-action="delete-arm-price" data-arm-id="${escapeHtml(item.id || "")}" data-price-key="${escapeHtml(key)}">删除</button>
              </label>
            `).join("") : `<div class="entity-meta">暂无价格版本。</div>`}
            <div class="price-add-row">
              <input placeholder="版本名" data-arm-price-name="${escapeHtml(item.id || "")}" />
              <input placeholder="价格，例如 ¥448,000" data-arm-price-value="${escapeHtml(item.id || "")}" />
              <button class="button button-secondary button-mini" type="button" data-catalog-action="add-arm-price" data-arm-id="${escapeHtml(item.id || "")}">添加</button>
            </div>
          </div>
        </div>
      </section>
    `;
  }
  if (editor.type === "option") {
    const item = findCatalogOption(editor.id);
    if (!item) return "";
    return `
      <section class="catalog-editor-card">
        <div class="catalog-editor-head">
          <div>
            <p class="eyebrow">Option editor</p>
            <h4>编辑选配：${escapeHtml(item.name || item.id || "-")}</h4>
            <p>选配价格、分类和说明会同步影响报价草案拆项。</p>
          </div>
          <button class="button button-secondary button-small" type="button" data-catalog-action="close-editor">收起编辑</button>
        </div>
        <div class="catalog-editor-body">
          <div class="option-inline-editor">
            <label class="field">
              <span>选配名称</span>
              <input data-catalog-action="option-field" data-option-id="${escapeHtml(item.id || "")}" data-field="name" value="${escapeHtml(item.name || "")}" />
            </label>
            <div class="form-grid form-grid-compact">
              <label class="field">
                <span>参考价格</span>
                <input data-catalog-action="option-field" data-option-id="${escapeHtml(item.id || "")}" data-field="reference_price" value="${escapeHtml(item.reference_price || "")}" />
              </label>
              <label class="field">
                <span>分类</span>
                <input data-catalog-action="option-field" data-option-id="${escapeHtml(item.id || "")}" data-field="category" value="${escapeHtml(item.category || "")}" />
              </label>
              <label class="field">
                <span>单位</span>
                <input data-catalog-action="option-field" data-option-id="${escapeHtml(item.id || "")}" data-field="unit" value="${escapeHtml(item.unit || "")}" />
              </label>
            </div>
            <label class="field">
              <span>说明</span>
              <textarea data-catalog-action="option-field" data-option-id="${escapeHtml(item.id || "")}" data-field="description" rows="3">${escapeHtml(item.description || "")}</textarea>
            </label>
            <button class="button button-danger button-small" type="button" data-catalog-action="delete-option" data-option-id="${escapeHtml(item.id || "")}">删除该选配</button>
          </div>
        </div>
      </section>
    `;
  }
  if (editor.type === "new-option") {
    return `
      <section class="catalog-editor-card">
        <div class="catalog-editor-head">
          <div>
            <p class="eyebrow">New option</p>
            <h4>新增选配</h4>
            <p>新增后会出现在选配卡片区，可继续加入某个版本包的必选或推荐配置。</p>
          </div>
          <button class="button button-secondary button-small" type="button" data-catalog-action="close-editor">取消</button>
        </div>
        <div class="option-add-grid">
          <input id="catalogNewOptionId" placeholder="选配 ID，例如 stream_deck_mini" />
          <input id="catalogNewOptionName" placeholder="选配名称" />
          <input id="catalogNewOptionPrice" placeholder="参考价格，例如 ¥10,000" />
          <input id="catalogNewOptionCategory" placeholder="分类，例如 control" />
          <input id="catalogNewOptionUnit" placeholder="单位，例如 套" />
          <button class="button button-primary" type="button" data-catalog-action="add-option">添加选配</button>
        </div>
      </section>
    `;
  }
  return "";
}

function renderCatalogModal(catalog, selectedPackage, armOptions, priceVersions) {
  const content = renderCatalogEditorCard(catalog, selectedPackage, armOptions, priceVersions);
  if (!content) return "";
  return `
    <div class="catalog-modal-backdrop" data-catalog-action="modal-backdrop">
      <div class="catalog-modal-card" role="dialog" aria-modal="true" aria-label="报价规则编辑">
        ${content}
      </div>
    </div>
  `;
}

function optionNameById(optionId, catalog = state.quoteCatalog) {
  const option = (catalog.options || []).find((item) => item.id === optionId);
  return option?.name || optionId;
}

function renderInspectorOptionList(ids = [], catalog = state.quoteCatalog) {
  if (!ids.length) return `<div class="entity-meta">暂无配置。</div>`;
  return `
    <div class="inspector-pill-list">
      ${ids.map((id) => `<span>${escapeHtml(optionNameById(id, catalog))}</span>`).join("")}
    </div>
  `;
}

function renderCatalogInspector(catalog, selectedPackage) {
  const focus = state.catalogFocus || { type: "package", id: selectedPackage?.id || "" };
  const packages = catalog.packages || [];
  const arms = catalog.arms || [];
  const options = catalog.options || [];
  let title = "当前版本包";
  let body = "";
  if (focus.type === "arm") {
    const arm = findCatalogArm(focus.id) || arms[0];
    title = "当前机械臂";
    body = arm ? `
      <div class="inspector-hero">
        <h4>${escapeHtml(arm.name || arm.id || "-")}</h4>
        ${tag(arm.id || "ARM")}
      </div>
      <div class="inspector-kv"><span>臂展</span><strong>${escapeHtml(arm.span || "-")}</strong></div>
      <div class="inspector-kv"><span>负载</span><strong>${escapeHtml(arm.payload || "-")}</strong></div>
      <div class="inspector-copy">${escapeHtml(arm.description || "-")}</div>
      <div class="catalog-editor-title">价格版本</div>
      <div class="inspector-price-list">
        ${Object.entries(arm.prices || {}).map(([key, value]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></div>`).join("") || `<div class="entity-meta">暂无价格。</div>`}
      </div>
      <button class="button button-secondary catalog-edit-btn" type="button" data-catalog-action="edit-arm" data-arm-id="${escapeHtml(arm.id || "")}">编辑价格</button>
    ` : emptyState("暂无机械臂。");
  } else if (focus.type === "option") {
    const option = findCatalogOption(focus.id) || options[0];
    title = "当前选配";
    body = option ? `
      <div class="inspector-hero">
        <h4>${escapeHtml(option.name || option.id || "-")}</h4>
        ${tag(option.reference_price || "未标价")}
      </div>
      <div class="inspector-kv"><span>分类</span><strong>${escapeHtml(option.category || "-")}</strong></div>
      <div class="inspector-kv"><span>单位</span><strong>${escapeHtml(option.unit || "-")}</strong></div>
      <div class="inspector-copy">${escapeHtml(option.description || "-")}</div>
      <button class="button button-secondary catalog-edit-btn" type="button" data-catalog-action="edit-option" data-option-id="${escapeHtml(option.id || "")}">编辑选配</button>
    ` : emptyState("暂无选配。");
  } else {
    const pkg = findCatalogPackage(focus.id) || selectedPackage || packages[0];
    title = "当前版本包";
    body = pkg ? `
      <div class="inspector-hero">
        <h4>${escapeHtml(pkg.name || pkg.id || "-")}</h4>
        ${tag(pkg.default_arm || "未配置臂型")}
      </div>
      <div class="inspector-kv"><span>适用场景</span><strong>${escapeHtml(pkg.scenario || "-")}</strong></div>
      <div class="inspector-kv"><span>价格版本</span><strong>${escapeHtml(pkg.price_version || "-")}</strong></div>
      <div class="inspector-copy">${escapeHtml(pkg.description || "-")}</div>
      <div class="catalog-editor-title">必选配件（${pkg.required_options?.length || 0}）</div>
      ${renderInspectorOptionList(pkg.required_options || [], catalog)}
      <div class="catalog-editor-title">推荐配件（${pkg.recommended_options?.length || 0}）</div>
      ${renderInspectorOptionList(pkg.recommended_options || [], catalog)}
      <button class="button button-secondary catalog-edit-btn" type="button" data-catalog-action="edit-package" data-package-id="${escapeHtml(pkg.id || "")}">编辑版本包</button>
    ` : emptyState("暂无版本包。");
  }
  return `
    <div class="catalog-inspector-card">
      <div class="catalog-inspector-head">
        <div>
          <p class="eyebrow">Inspector</p>
          <h3>${escapeHtml(title)}</h3>
        </div>
        ${statePill(state.catalogEditor ? "编辑中" : "预览", state.catalogEditor ? "warn" : "muted")}
      </div>
      ${body}
      <div class="catalog-inspector-summary">
        <div><span>臂型</span><strong>${arms.length}</strong></div>
        <div><span>版本包</span><strong>${packages.length}</strong></div>
        <div><span>选配</span><strong>${options.length}</strong></div>
      </div>
      <details class="catalog-json-panel">
        <summary>高级 JSON</summary>
        <label class="field field-wide">
          <span>报价规则 JSON</span>
          <textarea id="salesCatalogJson" class="json-editor" rows="18">${escapeHtml(JSON.stringify(catalog, null, 2))}</textarea>
        </label>
      </details>
    </div>
  `;
}

async function saveSalesPolicy() {
  hideNotice("salesPolicyNotice");
  const btn = $("#salesPolicySaveBtn");
  const restore = setLoading(btn, "保存中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/quote-policies`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectSalesPolicyForm())
    });
    state.quotePolicy = data.item || collectSalesPolicyForm();
    renderSalesPolicyForm(state.quotePolicy);
    showNotice("salesPolicyNotice", "报价策略已保存。", "success");
  } catch (e) {
    showNotice("salesPolicyNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

function renderQuoteCatalog(catalog) {
  const el = $("#salesCatalogList");
  const meta = $("#salesCatalogMeta");
  state.quoteCatalog = normalizeQuoteCatalog(catalog);
  catalog = state.quoteCatalog;
  const arms = catalog.arms || [];
  const packages = catalog.packages || [];
  const options = catalog.options || [];
  if (!state.selectedQuotePackageId && packages.length) {
    state.selectedQuotePackageId = packages[0].id || "";
  }
  if (state.selectedQuotePackageId && !packages.some((item) => item.id === state.selectedQuotePackageId)) {
    state.selectedQuotePackageId = packages[0]?.id || "";
  }
  if (!state.catalogFocus?.id && state.selectedQuotePackageId) {
    state.catalogFocus = { type: "package", id: state.selectedQuotePackageId };
  }
  const selectedPackage = getSelectedPackage(catalog);
  if (meta) {
    meta.textContent = `臂型 ${arms.length} 条，版本包 ${packages.length} 条，选配 ${options.length} 条${catalog.updated_at ? ` ｜ 更新时间：${catalog.updated_at}` : ""}`;
  }
  syncQuoteCatalogJson();
  if (!el) return;
  if (!arms.length && !packages.length && !options.length) {
    el.innerHTML = emptyState("暂无报价规则。");
    return;
  }
  const armOptions = arms.map((arm) => `<option value="${escapeHtml(arm.id || "")}">${escapeHtml(arm.id || arm.name || "-")}</option>`).join("");
  const priceVersions = Array.from(new Set([
    ...arms.flatMap((arm) => Object.keys(arm.prices || {})),
    ...packages.map((pkg) => pkg.price_version).filter(Boolean)
  ]));
  const inspector = $("#salesCatalogInspector");
  if (inspector) inspector.innerHTML = renderCatalogInspector(catalog, selectedPackage);
  const modal = $("#salesCatalogModal");
  if (modal) modal.innerHTML = renderCatalogModal(catalog, selectedPackage, armOptions, priceVersions);
  const packageCards = packages.map((item) => {
    const focused = state.catalogFocus?.type === "package" && state.catalogFocus.id === item.id;
    const linked = selectedPackage?.id === item.id && !focused;
    return `
    <div class="entity-card catalog-card package-card ${focused ? "catalog-card-active" : ""} ${linked ? "catalog-card-linked" : ""}" data-package-id="${escapeHtml(item.id || "")}">
      <button class="catalog-card-main" type="button" data-catalog-action="select-package" data-package-id="${escapeHtml(item.id || "")}">
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.name || item.id || "-")}</h4>
          ${tag(item.default_arm || "未配置臂型")}
        </div>
        <div class="entity-meta">${escapeHtml(item.scenario || "-")} ｜ 价格版本：${escapeHtml(item.price_version || "-")}</div>
      </button>
      <div class="entity-body">${escapeHtml(item.description || "")}</div>
      <div class="catalog-preview-meta">
        <span>必选 ${item.required_options?.length || 0} 项</span>
        <span>推荐 ${item.recommended_options?.length || 0} 项</span>
      </div>
      <button class="button button-secondary button-small catalog-edit-btn" type="button" data-catalog-action="edit-package" data-package-id="${escapeHtml(item.id || "")}">编辑</button>
    </div>
  `;
  }).join("");
  const armCards = arms.map((item) => {
    const priceText = Object.entries(item.prices || {}).map(([key, value]) => `${key} ${value}`).join("；");
    const focused = state.catalogFocus?.type === "arm" && state.catalogFocus.id === item.id;
    return `
      <div class="entity-card catalog-card arm-card ${focused ? "catalog-card-active" : ""}" data-arm="${escapeHtml(item.id || "")}">
        <button class="catalog-card-main" type="button" data-catalog-action="select-arm" data-arm-id="${escapeHtml(item.id || "")}">
          <div class="entity-title-row">
            <h4 class="entity-title">${escapeHtml(item.name || item.id || "-")}</h4>
            ${tag(item.id || "ARM")}
          </div>
          <div class="entity-meta">${escapeHtml(item.span || "-")} ｜ ${escapeHtml(item.payload || "-")}</div>
          <div class="entity-body">${escapeHtml(item.description || "")}</div>
          <div class="entity-meta">${escapeHtml(priceText || "暂无价格版本")}</div>
        </button>
        <button class="button button-secondary button-small catalog-edit-btn" type="button" data-catalog-action="edit-arm" data-arm-id="${escapeHtml(item.id || "")}">编辑价格</button>
      </div>
    `;
  }).join("");
  const optionCards = options.map((item) => {
    const membership = optionMembership(item.id, selectedPackage);
    const focused = state.catalogFocus?.type === "option" && state.catalogFocus.id === item.id;
    return `
    <div class="entity-card catalog-card option-card ${membership ? "catalog-card-included" : ""} ${focused ? "catalog-card-active" : ""}" data-option-id="${escapeHtml(item.id || "")}">
      <button class="catalog-card-main" type="button" data-catalog-action="select-option" data-option-id="${escapeHtml(item.id || "")}">
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.name || "-")}</h4>
          ${membership ? tag(membership) : tag(item.reference_price || "未标价")}
        </div>
        <div class="entity-meta">分类：${escapeHtml(item.category || "-")} ｜ 单位：${escapeHtml(item.unit || "-")}</div>
        <div class="entity-body">${escapeHtml(item.description || "")}</div>
        <div class="entity-meta">价格：${escapeHtml(item.reference_price || "未标价")}</div>
      </button>
      <button class="button button-secondary button-small catalog-edit-btn" type="button" data-catalog-action="edit-option" data-option-id="${escapeHtml(item.id || "")}">编辑选配</button>
    </div>
  `;
  }).join("");
  el.innerHTML = `
    <div class="catalog-section-title">版本包</div>
    <div class="catalog-card-grid package-grid">${packageCards}</div>
    <div class="catalog-section-title">臂型维护</div>
    <div class="catalog-card-grid arm-grid">${armCards}</div>
    <div class="catalog-section-title catalog-section-title-row">
      <span>附加选配维护</span>
      <button class="button button-secondary button-small" type="button" data-catalog-action="open-new-option">新增选配</button>
    </div>
    <div class="catalog-card-grid option-grid">${optionCards}</div>
  `;
  $all('[data-catalog-action="package-field"][data-field="default_arm"]').forEach((select) => {
    const pkg = packages.find((item) => item.id === select.dataset.packageId);
    select.value = pkg?.default_arm || "";
  });
  $all('[data-catalog-action="package-field"][data-field="price_version"]').forEach((select) => {
    const pkg = packages.find((item) => item.id === select.dataset.packageId);
    select.value = pkg?.price_version || "";
  });
  syncQuoteCatalogJson();
}

function findCatalogPackage(id) {
  return (state.quoteCatalog.packages || []).find((item) => item.id === id);
}

function findCatalogArm(id) {
  return (state.quoteCatalog.arms || []).find((item) => item.id === id);
}

function findCatalogOption(id) {
  return (state.quoteCatalog.options || []).find((item) => item.id === id);
}

function handleCatalogFieldInput(event) {
  const target = event.target;
  const action = target?.dataset?.catalogAction;
  if (!action) return;
  if (action === "package-field") {
    const pkg = findCatalogPackage(target.dataset.packageId);
    if (!pkg) return;
    pkg[target.dataset.field] = target.value;
    setQuoteCatalogDirty();
  } else if (action === "package-list-field") {
    const pkg = findCatalogPackage(target.dataset.packageId);
    if (!pkg) return;
    pkg[target.dataset.field] = splitWords(target.value);
    setQuoteCatalogDirty();
  } else if (action === "arm-price") {
    const arm = findCatalogArm(target.dataset.armId);
    if (!arm) return;
    arm.prices = arm.prices || {};
    arm.prices[target.dataset.priceKey] = target.value;
    setQuoteCatalogDirty();
  } else if (action === "option-field") {
    const option = findCatalogOption(target.dataset.optionId);
    if (!option) return;
    option[target.dataset.field] = target.value;
    setQuoteCatalogDirty();
  }
}

function handleCatalogFieldChange(event) {
  const target = event.target;
  const action = target?.dataset?.catalogAction;
  if (action !== "package-option") return;
  const pkg = findCatalogPackage(target.dataset.packageId);
  if (!pkg) return;
  updatePackageOptionMembership(pkg, target.dataset.optionId, target.dataset.bucket, target.checked);
  setQuoteCatalogDirty("版本包配件已同步，选配卡片已按当前版本包高亮。");
  renderQuoteCatalog(state.quoteCatalog);
}

function addCatalogArmPrice(armId) {
  const arm = findCatalogArm(armId);
  if (!arm) return;
  const name = $all("[data-arm-price-name]").find((input) => input.dataset.armPriceName === armId)?.value.trim() || "";
  const value = $all("[data-arm-price-value]").find((input) => input.dataset.armPriceValue === armId)?.value.trim() || "";
  if (!name || !value) {
    showNotice("salesCatalogNotice", "请填写版本名和价格。", "error");
    return;
  }
  arm.prices = arm.prices || {};
  arm.prices[name] = value;
  setQuoteCatalogDirty("机械臂价格版本已添加。");
  renderQuoteCatalog(state.quoteCatalog);
}

function addCatalogOption() {
  const idInput = $("#catalogNewOptionId");
  const nameInput = $("#catalogNewOptionName");
  const priceInput = $("#catalogNewOptionPrice");
  const categoryInput = $("#catalogNewOptionCategory");
  const unitInput = $("#catalogNewOptionUnit");
  const id = (idInput?.value.trim() || `option_${Date.now()}`).replace(/\s+/g, "_");
  if ((state.quoteCatalog.options || []).some((item) => item.id === id)) {
    showNotice("salesCatalogNotice", "这个选配 ID 已存在，请换一个 ID。", "error");
    return;
  }
  state.quoteCatalog.options = state.quoteCatalog.options || [];
  state.quoteCatalog.options.push({
    id,
    name: nameInput?.value.trim() || id,
    category: categoryInput?.value.trim() || "accessory",
    unit: unitInput?.value.trim() || "套",
    reference_price: priceInput?.value.trim() || "需按最终配置核算",
    description: ""
  });
  state.catalogFocus = { type: "option", id };
  state.catalogEditor = { type: "option", id };
  setQuoteCatalogDirty("新选配已添加，可以在卡片里继续补充说明或加入版本包。");
  renderQuoteCatalog(state.quoteCatalog);
}

function handleCatalogClick(event) {
  const control = event.target.closest("[data-catalog-action]");
  if (!control) return;
  const action = control.dataset.catalogAction;
  if (action === "select-package") {
    event.preventDefault();
    const id = control.dataset.packageId || "";
    if (id) {
      state.selectedQuotePackageId = id;
      state.catalogFocus = { type: "package", id };
      renderQuoteCatalog(state.quoteCatalog);
    }
    return;
  }
  if (action === "select-arm") {
    state.catalogFocus = { type: "arm", id: control.dataset.armId || "" };
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "select-option") {
    state.catalogFocus = { type: "option", id: control.dataset.optionId || "" };
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "edit-package") {
    state.selectedQuotePackageId = control.dataset.packageId || state.selectedQuotePackageId;
    state.catalogFocus = { type: "package", id: control.dataset.packageId || "" };
    state.catalogEditor = { type: "package", id: control.dataset.packageId || "" };
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "edit-arm") {
    state.catalogFocus = { type: "arm", id: control.dataset.armId || "" };
    state.catalogEditor = { type: "arm", id: control.dataset.armId || "" };
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "edit-option") {
    state.catalogFocus = { type: "option", id: control.dataset.optionId || "" };
    state.catalogEditor = { type: "option", id: control.dataset.optionId || "" };
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "open-new-option") {
    state.catalogEditor = { type: "new-option", id: "" };
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "modal-backdrop") {
    if (event.target === control) {
      state.catalogEditor = null;
      renderQuoteCatalog(state.quoteCatalog);
    }
    return;
  }
  if (action === "close-editor") {
    state.catalogEditor = null;
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "add-arm-price") {
    addCatalogArmPrice(control.dataset.armId);
    return;
  }
  if (action === "delete-arm-price") {
    const arm = findCatalogArm(control.dataset.armId);
    if (!arm?.prices) return;
    delete arm.prices[control.dataset.priceKey];
    setQuoteCatalogDirty("机械臂价格版本已删除。");
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "delete-option") {
    const optionId = control.dataset.optionId;
    if (!optionId) return;
    if (!confirm("确定删除这个选配吗？它也会从所有版本包的必选/推荐配置里移除。")) return;
    state.quoteCatalog.options = (state.quoteCatalog.options || []).filter((item) => item.id !== optionId);
    removeOptionEverywhere(optionId);
    state.catalogEditor = null;
    if (state.catalogFocus?.type === "option" && state.catalogFocus.id === optionId) {
      state.catalogFocus = { type: "package", id: state.selectedQuotePackageId || "" };
    }
    setQuoteCatalogDirty("选配已删除，并已从版本包配置中同步移除。");
    renderQuoteCatalog(state.quoteCatalog);
    return;
  }
  if (action === "add-option") {
    addCatalogOption();
  }
}

function collectQuoteCatalogEditor() {
  try {
    const catalog = normalizeQuoteCatalog(JSON.parse($("#salesCatalogJson")?.value || "{}"));
    state.quoteCatalog = catalog;
    if (state.catalogEditor) {
      const found = (
        (state.catalogEditor.type === "package" && catalog.packages.some((item) => item.id === state.catalogEditor.id)) ||
        (state.catalogEditor.type === "arm" && catalog.arms.some((item) => item.id === state.catalogEditor.id)) ||
        (state.catalogEditor.type === "option" && catalog.options.some((item) => item.id === state.catalogEditor.id)) ||
        state.catalogEditor.type === "new-option"
      );
      if (!found) state.catalogEditor = null;
    }
    return catalog;
  } catch (e) {
    throw new Error(`JSON 解析失败：${e.message}`);
  }
}

async function validateSalesCatalog() {
  let payload;
  try {
    payload = collectQuoteCatalogEditor();
  } catch (e) {
    showNotice("salesCatalogNotice", e.message, "error");
    return;
  }
  const btn = $("#salesCatalogValidateBtn");
  const restore = setLoading(btn, "校验中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/quote-catalog/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const warnings = (data.warnings || []).join("；");
    showNotice("salesCatalogNotice", data.ok ? (warnings ? `校验通过，提醒：${warnings}` : "校验通过。") : `校验失败：${(data.errors || []).join("；")}`, data.ok ? "success" : "error");
  } catch (e) {
    showNotice("salesCatalogNotice", `校验失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function saveSalesCatalog() {
  let payload;
  try {
    payload = collectQuoteCatalogEditor();
  } catch (e) {
    showNotice("salesCatalogNotice", e.message, "error");
    return;
  }
  const btn = $("#salesCatalogSaveBtn");
  const restore = setLoading(btn, "保存中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/quote-catalog`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    state.quoteCatalog = normalizeQuoteCatalog(data.item || payload);
    renderQuoteCatalog(state.quoteCatalog);
    showNotice("salesCatalogNotice", "报价规则库已保存，聊天报价会立即使用新规则。", "success");
  } catch (e) {
    showNotice("salesCatalogNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function clearQuoteReferenceDocs() {
  if (!confirm("确定清理项目内已导入的旧报价参考文档、解析结果和文档向量索引吗？下载目录原始文件不会删除。")) return;
  const btn = $("#salesClearQuoteDocsBtn");
  const restore = setLoading(btn, "清理中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/docs/clear-quote-references`, { method: "POST" });
    showNotice("salesCatalogNotice", `已清理 ${data.deleted_chunk_count || 0} 个文档片段、${data.removed_file_count || 0} 个文件。${data.index_error ? `向量索引清理提示：${data.index_error}` : ""}`, data.index_error ? "info" : "success");
    await loadSummary().catch(() => null);
  } catch (e) {
    showNotice("salesCatalogNotice", `清理失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

function renderQuoteArchives(items, total) {
  const el = $("#salesArchiveList");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = emptyState("暂无报价档案。带 user_id 的报价咨询会自动生成草案。");
    return;
  }
  el.innerHTML = items.slice(0, 80).map((item) => `
    <details class="entity-card">
      <summary>
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.user_id || "-")}</h4>
          ${tag(item.status || "draft")}
        </div>
        <div class="entity-meta">${escapeHtml(item.channel || "api")} ｜ 更新时间：${escapeHtml(item.updated_at || "-")}</div>
      </summary>
      <div class="entity-body">${escapeHtml(item.need_summary || "-")}</div>
      <div class="entity-meta">推荐：${escapeHtml(formatList(item.recommended_products || []))}</div>
      <div class="entity-meta">参考总价：${escapeHtml(item.reference_total || "-")}</div>
    </details>
  `).join("");
}

async function searchQuoteArchives() {
  const q = $("#salesArchiveSearch")?.value.trim() || "";
  const data = await fetchJson(`${ADMIN_API}/quote-archives?q=${encodeURIComponent(q)}`);
  renderQuoteArchives(data.items || [], data.total || 0);
}

async function loadTrainingPage() {
  const [rules, styles, cases] = await Promise.all([
    fetchJson(`${ADMIN_API}/behavior-rules`),
    fetchJson(`${ADMIN_API}/answer-styles`),
    fetchJson(`${ADMIN_API}/regression-cases`)
  ]);
  state.behaviorRules = rules || {};
  state.answerStyles = styles || {};
  renderTrainingBehaviorForm();
  renderTrainingAnswerForm();
  renderTrainingCases(cases.items || [], cases.total || cases.items?.length || 0);
}

function renderTrainingBehaviorForm() {
  const rules = state.behaviorRules || {};
  const memory = rules.memory_policy || {};
  const fallback = rules.fallback_policy || {};
  $("#trainingBehaviorForm").innerHTML = `
    <label class="settings-row toggle-field">
      <input id="trainingPreviousProduct" type="checkbox" ${memory.previous_product_anchor !== false ? "checked" : ""} />
      <span><strong>上次产品优先</strong><br><small>客户问上次、之前、那个产品时优先读取客户记忆。</small></span>
    </label>
    <label class="settings-row toggle-field">
      <input id="trainingActiveGap" type="checkbox" ${fallback.active_gap_prompt_on_test_page !== false ? "checked" : ""} />
      <span><strong>资料不足主动追问</strong><br><small>命中不可靠时说明缺少什么资料。</small></span>
    </label>
    <label class="field">
      <span>上下文触发词</span>
      <input id="trainingContextWords" value="${escapeHtml(joinWords(memory.previous_context_words || []))}" />
    </label>
    <label class="field">
      <span>产品回忆问法</span>
      <input id="trainingRecallWords" value="${escapeHtml(joinWords(memory.product_recall_words || []))}" />
    </label>
  `;
}

function renderTrainingAnswerForm() {
  const styles = state.answerStyles || {};
  $("#trainingAnswerForm").innerHTML = `
    <label class="field">
      <span>资料不足时怎么说</span>
      <textarea id="trainingFallbackTemplate" rows="5">${escapeHtml(styles.fallback_gap_template || "")}</textarea>
    </label>
    <label class="field">
      <span>引用客户记忆时怎么说</span>
      <textarea id="trainingMemoryTemplate" rows="4">${escapeHtml(styles.memory_recall_template || "")}</textarea>
    </label>
    <label class="field">
      <span>报价免责声明</span>
      <textarea id="trainingQuoteDisclaimer" rows="4">${escapeHtml(styles.quote_disclaimer || "")}</textarea>
    </label>
  `;
}

function collectBehaviorRulesForm() {
  return {
    ...(state.behaviorRules || {}),
    memory_policy: {
      ...((state.behaviorRules || {}).memory_policy || {}),
      previous_context_words: splitWords($("#trainingContextWords")?.value || ""),
      product_recall_words: splitWords($("#trainingRecallWords")?.value || ""),
      previous_product_anchor: Boolean($("#trainingPreviousProduct")?.checked)
    },
    fallback_policy: {
      ...((state.behaviorRules || {}).fallback_policy || {}),
      active_gap_prompt_on_test_page: Boolean($("#trainingActiveGap")?.checked)
    }
  };
}

function collectAnswerStylesForm() {
  return {
    ...(state.answerStyles || {}),
    fallback_gap_template: $("#trainingFallbackTemplate")?.value || "",
    memory_recall_template: $("#trainingMemoryTemplate")?.value || "",
    quote_disclaimer: $("#trainingQuoteDisclaimer")?.value || ""
  };
}

async function saveTrainingBehavior() {
  const btn = $("#trainingBehaviorSaveBtn");
  const restore = setLoading(btn, "保存中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/behavior-rules`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectBehaviorRulesForm())
    });
    state.behaviorRules = data.item || collectBehaviorRulesForm();
    renderTrainingBehaviorForm();
    showNotice("trainingNotice", "行为规则已保存。", "success");
  } catch (e) {
    showNotice("trainingNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function saveTrainingAnswer() {
  const btn = $("#trainingAnswerSaveBtn");
  const restore = setLoading(btn, "保存中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/answer-styles`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectAnswerStylesForm())
    });
    state.answerStyles = data.item || collectAnswerStylesForm();
    renderTrainingAnswerForm();
    showNotice("trainingNotice", "话术模板已保存。", "success");
  } catch (e) {
    showNotice("trainingNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

function renderTrainingCases(items, total) {
  const summary = $("#trainingTestSummary");
  const list = $("#trainingTestList");
  if (summary) summary.textContent = `当前回归测试 ${total || items.length || 0} 条。`;
  if (!list) return;
  if (!items.length) {
    list.innerHTML = emptyState("暂无回归测试用例。");
    return;
  }
  list.innerHTML = items.slice(0, 80).map((item) => `
    <div class="entity-card">
      <div class="entity-title-row">
        <h4 class="entity-title">${escapeHtml(item.name || item.id || "测试用例")}</h4>
        ${item.message ? tag(item.expected_route || item.route || "case") : statePill("无效用例", "bad")}
      </div>
      <div class="entity-meta">${escapeHtml(item.message || item.question || item.input || "")}</div>
    </div>
  `).join("");
}

async function createTrainingDraft() {
  const instruction = $("#trainingInstructionInput")?.value.trim();
  if (!instruction) {
    showNotice("trainingNotice", "请先输入优化指令。", "error");
    return;
  }
  const btn = $("#trainingDraftBtn");
  const restore = setLoading(btn, "生成中...");
  showNotice("trainingNotice", "正在生成草稿...", "loading");
  try {
    const data = await fetchJson(`${ADMIN_API}/tuning/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction })
    });
    state.trainingDraft = data.draft || null;
    $("#trainingDraftPreview").textContent = state.trainingDraft ? JSON.stringify(state.trainingDraft, null, 2) : "暂无草稿。";
    showNotice("trainingNotice", "草稿已生成。检查后可点击应用当前草稿。", "success");
  } catch (e) {
    showNotice("trainingNotice", `生成失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function applyTrainingDraft() {
  if (!state.trainingDraft) {
    showNotice("trainingNotice", "当前没有可应用的草稿。", "error");
    return;
  }
  const btn = $("#trainingApplyDraftBtn");
  const restore = setLoading(btn, "应用中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/tuning/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft: state.trainingDraft })
    });
    if (data.blocked) {
      const failed = data.regression_check?.failed || 0;
      showNotice("trainingNotice", `草稿未应用：当前有 ${failed} 条回归测试失败。请先查看测试结果，确认后再强制应用。`, "error");
      return;
    }
    state.trainingDraft = null;
    $("#trainingDraftPreview").textContent = "暂无草稿。";
    showNotice("trainingNotice", `草稿已应用，当前回归测试 ${data.regression_cases?.length || 0} 条。`, "success");
    await loadTrainingPage();
  } catch (e) {
    showNotice("trainingNotice", `应用失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function runTrainingTests() {
  const btn = $("#trainingRunTestsBtn");
  const restore = setLoading(btn, "运行中...");
  $("#trainingTestSummary").textContent = "正在运行测试集...";
  try {
    const data = await fetchJson(`${ADMIN_API}/regression-cases/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    $("#trainingTestSummary").textContent = `共 ${data.total || 0} 条，通过 ${data.passed || 0} 条，失败 ${data.failed || 0} 条。`;
    const results = data.results || [];
    $("#trainingTestList").innerHTML = results.length ? results.map((item) => `
      <div class="entity-card">
        <div class="entity-title-row">
          <h4 class="entity-title">${escapeHtml(item.name || item.id || "测试")}</h4>
          ${statePill(item.passed ? "通过" : "失败", item.passed ? "good" : "bad")}
        </div>
        <div class="entity-meta">route: ${escapeHtml(item.route || "-")} ｜ ${escapeHtml((item.failures || []).join("；"))}</div>
        <div class="entity-body">${escapeHtml((item.answer || "").slice(0, 260))}</div>
      </div>
    `).join("") : emptyState("暂无测试结果。");
  } catch (e) {
    $("#trainingTestSummary").textContent = `测试运行失败：${e.message}`;
  } finally {
    restore();
  }
}

async function loadRegressionPage() {
  const data = await loadRegressionCases();
  state.regressionCases = data.items || [];
  renderRegressionCaseTable(state.regressionCases);
  const summary = $("#regressionSummary");
  if (summary) summary.textContent = `当前回归测试 ${data.total || state.regressionCases.length || 0} 条。`;
}

function renderRegressionCaseTable(items = [], results = state.regressionResults || []) {
  const el = $("#regressionCaseTable");
  if (!el) return;
  const resultMap = new Map(results.map((item) => [item.id || item.name || item.message, item]));
  if (!items.length) {
    el.innerHTML = `<tr><td colspan="7">${emptyState("暂无回归测试用例。")}</td></tr>`;
    return;
  }
  el.innerHTML = items.map((item) => {
    const result = resultMap.get(item.id) || resultMap.get(item.name) || resultMap.get(item.message) || null;
    return `
      <tr>
        <td>${escapeHtml(item.message || item.question || "")}</td>
        <td>${escapeHtml(item.expected_route || "-")}</td>
        <td>${escapeHtml(item.expected_tool || "-")}</td>
        <td>${escapeHtml(joinWords(item.must_include || item.expected_keywords || []))}</td>
        <td>${escapeHtml(joinWords(item.must_not_include || item.forbidden_keywords || []))}</td>
        <td>${item.expected_need_human_review === undefined ? "-" : (item.expected_need_human_review ? "是" : "否")}</td>
        <td>${result ? statePill(result.passed ? "通过" : "失败", result.passed ? "good" : "bad") : statePill("未运行", "muted")}</td>
      </tr>
    `;
  }).join("");
}

async function runRegressionPageTests() {
  const btn = $("#regressionRunAllBtn");
  const restore = setLoading(btn, "运行中...");
  $("#regressionSummary").textContent = "正在运行全部回归测试...";
  try {
    const data = await fetchJson(`${ADMIN_API}/regression-cases/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    state.regressionResults = data.results || [];
    $("#regressionSummary").textContent = `共 ${data.total || 0} 条，通过 ${data.passed || 0} 条，失败 ${data.failed || 0} 条。`;
    renderRegressionCaseTable(state.regressionCases, state.regressionResults);
  } catch (e) {
    $("#regressionSummary").textContent = `运行失败：${e.message}`;
  } finally {
    restore();
  }
}

async function loadMemoryPage(q = "") {
  const data = await fetchJson(`${ADMIN_API}/memories${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  state.memories = data.items || [];
  renderMemoryList(state.memories, "memoryPageList");
}

async function searchMemoryPage() {
  await loadMemoryPage($("#memoryPageSearch")?.value.trim() || "");
}

async function loadDiagnosticsPage() {
  const [status, models, logs, launcher] = await Promise.all([
    loadStatus(),
    loadModels(),
    fetchJson(`${ADMIN_API}/logs`),
    fetchJson("/api/system/status").catch((e) => ({ offline: true, message: e.message }))
  ]);
  renderDiagnosticsStatus(status);
  renderDiagnosticsModels(models);
  renderDiagnosticsLauncher(launcher);
  $("#diagnosticsLogBox").textContent = logs.text || "暂无日志。";
}

function renderDiagnosticsStatus(status) {
  $("#diagnosticsStatusGrid").innerHTML = [
    metricCard("FastAPI", status.backend === "online" ? "在线" : "离线", status.base_dir || ""),
    metricCard("Ollama", status.ollama === "online" ? "在线" : "离线", "本地模型服务"),
    metricCard("Qdrant", status.qdrant === "online" ? "在线" : "离线", "向量检索服务"),
    metricCard("日志", status.log_path ? "可读取" : "未知", status.log_path || "")
  ].join("");
}

function renderDiagnosticsModels(models) {
  const settings = models.settings || {};
  const ollama = models.ollama || {};
  $("#diagnosticsModelPanel").innerHTML = [
    statusCard("Ollama 状态", ollama.online ? "在线" : "离线", ollama.online ? "good" : "bad", ollama.online ? `已安装 ${ollama.models?.length || 0} 个模型` : ollama.error || ""),
    statusCard("回答模型", settings.chat_model || "-", settings.chat_model ? "good" : "warn", "影响客服回答生成"),
    statusCard("向量模型", settings.embed_model || "-", settings.embed_model ? "good" : "warn", settings.embed_index_message || ""),
    statusCard("向量索引", settings.embed_index_status || "-", settings.embed_index_status === "success" ? "good" : "warn", "")
  ].join("");
}

function renderDiagnosticsLauncher(data) {
  const app = data.app || data;
  const qdrant = data.qdrant || {};
  const offline = data.offline;
  $("#diagnosticsLauncherPanel").innerHTML = [
    statusCard("启动器", offline ? "未启动" : "可用", offline ? "bad" : "good", data.message || data.base_dir || ""),
    statusCard("业务服务", app.running ? "运行中" : "未运行", runningType(app.running), app.pid ? `PID ${app.pid}` : ""),
    statusCard("Qdrant", qdrant.running ? "运行中" : "未知", qdrant.running ? "good" : "warn", qdrant.mode || ""),
    statusCard("Docker", qdrant.docker_ready ? "已就绪" : "未就绪", qdrant.docker_ready ? "good" : "warn", qdrant.docker_error || qdrant.docker_path || "")
  ].join("");
}

async function runSystemAction(action) {
  const button = document.querySelector(`[data-system-action="${action}"]`);
  const restore = setLoading(button, "执行中...");
  try {
    await fetchJson(`/api/system/${action}`, { method: "POST" });
    await loadDiagnosticsPage();
  } catch (e) {
    $("#diagnosticsLauncherPanel").insertAdjacentHTML("afterbegin", `<div class="notice error">操作失败：${escapeHtml(e.message)}</div>`);
  } finally {
    restore();
  }
}

async function loadSettingsPage() {
  const [models, behavior, answer, quote, quoteCatalog] = await Promise.all([
    loadModels(),
    fetchJson(`${ADMIN_API}/behavior-rules`),
    fetchJson(`${ADMIN_API}/answer-styles`),
    fetchJson(`${ADMIN_API}/quote-policies`),
    fetchJson(`${ADMIN_API}/quote-catalog`)
  ]);
  state.behaviorRules = behavior || {};
  state.answerStyles = answer || {};
  state.quotePolicy = quote || {};
  state.quoteCatalog = normalizeQuoteCatalog(quoteCatalog);
  renderModelSelects(models);
  renderSettingsJson();
}

function renderModelSelects(models) {
  const options = (models.ollama?.models || []).map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join("");
  const fallback = `<option value="">未读取到模型</option>`;
  $("#settingsChatModelSelect").innerHTML = options || fallback;
  $("#settingsEmbedModelSelect").innerHTML = options || fallback;
  $("#settingsChatModelSelect").value = models.settings?.chat_model || "";
  $("#settingsEmbedModelSelect").value = models.settings?.embed_model || "";
}

function renderSettingsJson() {
  $("#settingsBehaviorJson").value = JSON.stringify(state.behaviorRules || {}, null, 2);
  $("#settingsAnswerJson").value = JSON.stringify(state.answerStyles || {}, null, 2);
  $("#settingsQuotePolicyJson").value = JSON.stringify(state.quotePolicy || {}, null, 2);
  $("#settingsPricingJson").value = JSON.stringify(state.quoteCatalog || {}, null, 2);
}

async function saveChatModel() {
  const model = $("#settingsChatModelSelect")?.value;
  if (!model) {
    showNotice("settingsChatNotice", "请选择回答模型。", "error");
    return;
  }
  const btn = $("#settingsChatModelSaveBtn");
  const restore = setLoading(btn, "保存中...");
  try {
    await fetchJson(`${ADMIN_API}/models/chat`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_model: model })
    });
    showNotice("settingsChatNotice", `回答模型已切换为：${model}`, "success");
    await loadModels();
  } catch (e) {
    showNotice("settingsChatNotice", `保存失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function rebuildEmbedModel() {
  const model = $("#settingsEmbedModelSelect")?.value;
  if (!model) {
    showNotice("settingsEmbedNotice", "请选择向量模型。", "error");
    return;
  }
  if (!confirm(`确定切换向量模型为 ${model} 并重建 FAQ 和文档向量库吗？`)) return;
  const btn = $("#settingsEmbedRebuildBtn");
  const restore = setLoading(btn, "重建中...");
  try {
    const data = await fetchJson(`${ADMIN_API}/models/embed/rebuild`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ embed_model: model })
    });
    showNotice("settingsEmbedNotice", data.settings?.embed_index_message || "向量库已重建。", "success");
    await loadModels();
  } catch (e) {
    showNotice("settingsEmbedNotice", `重建失败：${e.message}`, "error");
  } finally {
    restore();
  }
}

async function saveJsonConfig(id, endpoint, notice = "settingsJsonNotice") {
  const el = document.getElementById(id);
  let payload;
  try {
    payload = JSON.parse(el?.value || "{}");
  } catch (e) {
    showNotice(notice, `JSON 解析失败：${e.message}`, "error");
    return;
  }
  try {
    await fetchJson(`${ADMIN_API}/${endpoint}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    showNotice(notice, "JSON 已保存。", "success");
  } catch (e) {
    showNotice(notice, `保存失败：${e.message}`, "error");
  }
}

function bindEvents() {
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.docChunkModal) {
      closeDocChunkModal();
      return;
    }
    if (event.key === "Escape" && state.catalogEditor) {
      state.catalogEditor = null;
      renderQuoteCatalog(state.quoteCatalog);
    }
  });
  $("#refreshPageBtn")?.addEventListener("click", () => loadCurrentPage());
  $("#qualityTestForm")?.addEventListener("submit", runQualityTest);
  $("#qualityRunRegressionBtn")?.addEventListener("click", runQualityRegression);
  $("#qualityReloadFeedbackBtn")?.addEventListener("click", reloadQualityFeedback);
  $("#qualityFeedbackRegressionBtn")?.addEventListener("click", () => saveQualityFeedback("good", true));
  $all("[data-quality-filter]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.qualityFilter = button.dataset.qualityFilter || "";
      $all("[data-quality-filter]").forEach((node) => node.classList.toggle("active", node === button));
      await reloadQualityRecords();
    });
  });
  $("#qualityRecordList")?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-quality-record-id]");
    if (!card) return;
    state.selectedQualityRecord = state.qualityRecords.find((item) => item.id === card.dataset.qualityRecordId) || null;
    renderQualityRecordList(state.qualityRecords);
    renderQualityDrawer(state.selectedQualityRecord);
  });
  $("#qualityDetailDrawer")?.addEventListener("click", async (event) => {
    if (!state.selectedQualityRecord?.id) return;
    const annotation = event.target.closest("[data-quality-annotation]");
    if (annotation) {
      await updateQualityRecord(state.selectedQualityRecord.id, { human_annotation: annotation.dataset.qualityAnnotation });
      return;
    }
    const fix = event.target.closest("[data-quality-fix]");
    if (!fix) return;
    const action = fix.dataset.qualityFix || "";
    if (action === "add_regression_case") {
      await feedbackToRegressionCase(state.selectedQualityRecord.id);
      await reloadQualityRecords();
      return;
    }
    if (action === "resolved") {
      await updateQualityRecord(state.selectedQualityRecord.id, { status: "resolved" });
      return;
    }
    await updateQualityRecord(state.selectedQualityRecord.id, { suggested_action: action, status: "pending" });
  });
  document.querySelectorAll("[data-quality-feedback]").forEach((button) => {
    button.addEventListener("click", () => saveQualityFeedback(button.dataset.qualityFeedback || "needs_review"));
  });
  $("#regressionRunAllBtn")?.addEventListener("click", runRegressionPageTests);
  $("#knowledgeReloadBtn")?.addEventListener("click", loadKnowledgePage);
  $("#knowledgeIndexReloadBtn")?.addEventListener("click", async () => {
    const data = await fetchJson(`${ADMIN_API}/knowledge-index-status`);
    state.knowledgeIndexStatus = data;
    renderIndexStatus("knowledgeIndexStatus", data);
  });
  $("#knowledgeDocUploadForm")?.addEventListener("submit", uploadKnowledgeDocs);
  $("#knowledgeDocSemanticRebuildBtn")?.addEventListener("click", rebuildSemanticDocs);
  $("#knowledgeDocSearchBtn")?.addEventListener("click", searchKnowledgeDocs);
  $("#knowledgeDocsList")?.addEventListener("click", (event) => {
    const pageButton = event.target.closest("[data-doc-page]");
    if (pageButton) {
      event.preventDefault();
      event.stopPropagation();
      setDocPage(pageButton.dataset.docPage || "", Number(pageButton.dataset.page || 1));
      return;
    }
    const card = event.target.closest("[data-doc-chunk-id]");
    if (card) openDocChunkModal(card.dataset.docChunkId || "");
  });
  document.body.addEventListener("click", (event) => {
    const actionEl = event.target.closest("[data-doc-modal-action]");
    if (!actionEl) return;
    if (actionEl.classList.contains("doc-modal-backdrop") && event.target !== actionEl) return;
    if (actionEl.dataset.docModalAction === "close") closeDocChunkModal();
  });
  $("#knowledgeFaqForm")?.addEventListener("submit", saveKnowledgeFaq);
  $("#knowledgeFaqNewBtn")?.addEventListener("click", () => fillFaqForm(null));
  $("#knowledgeFaqDuplicateBtn")?.addEventListener("click", () => saveKnowledgeFaq(null, true));
  $("#knowledgeFaqDeleteBtn")?.addEventListener("click", deleteKnowledgeFaq);
  $("#knowledgeFaqReindexBtn")?.addEventListener("click", reindexKnowledgeFaqs);
  $("#knowledgeRuleForm")?.addEventListener("submit", saveKnowledgeRule);
  $("#knowledgeRuleNewBtn")?.addEventListener("click", () => fillRuleForm(null));
  $("#knowledgeRuleDuplicateBtn")?.addEventListener("click", () => saveKnowledgeRule(null, true));
  $("#knowledgeRuleDeleteBtn")?.addEventListener("click", deleteKnowledgeRule);
  $("#knowledgeRuleTestBtn")?.addEventListener("click", testKnowledgeRule);
  $("#knowledgeMemoryForm")?.addEventListener("submit", saveKnowledgeMemory);
  $("#knowledgeMemorySearchBtn")?.addEventListener("click", searchKnowledgeMemories);
  $("#knowledgeMemoryNewBtn")?.addEventListener("click", () => fillMemoryForm(null));
  $("#knowledgeMemoryDeleteBtn")?.addEventListener("click", deleteKnowledgeMemory);
  $("#memoryPageSearchBtn")?.addEventListener("click", searchMemoryPage);
  $("#knowledgeLearnedSearchBtn")?.addEventListener("click", searchLearnedKnowledge);
  $("#knowledgeLearnedReindexBtn")?.addEventListener("click", reindexLearnedKnowledge);
  $("#configQuoteForm")?.addEventListener("submit", draftConfigQuote);
  $("#salesPolicySaveBtn")?.addEventListener("click", saveSalesPolicy);
  ["salesCatalogList", "salesCatalogInspector", "salesCatalogModal"].forEach((id) => {
    const node = document.getElementById(id);
    node?.addEventListener("input", handleCatalogFieldInput);
    node?.addEventListener("change", handleCatalogFieldChange);
    node?.addEventListener("click", handleCatalogClick);
  });
  $("#salesCatalogValidateBtn")?.addEventListener("click", validateSalesCatalog);
  $("#salesCatalogSaveBtn")?.addEventListener("click", saveSalesCatalog);
  $("#salesClearQuoteDocsBtn")?.addEventListener("click", clearQuoteReferenceDocs);
  $("#salesClearQuoteDocsBtnTop")?.addEventListener("click", clearQuoteReferenceDocs);
  $("#salesArchiveSearchBtn")?.addEventListener("click", searchQuoteArchives);
  $("#trainingDraftBtn")?.addEventListener("click", createTrainingDraft);
  $("#trainingApplyDraftBtn")?.addEventListener("click", applyTrainingDraft);
  $("#trainingRunTestsBtn")?.addEventListener("click", runTrainingTests);
  $("#trainingBehaviorSaveBtn")?.addEventListener("click", saveTrainingBehavior);
  $("#trainingAnswerSaveBtn")?.addEventListener("click", saveTrainingAnswer);
  $("#diagnosticsReloadBtn")?.addEventListener("click", loadDiagnosticsPage);
  $all("[data-system-action]").forEach((button) => {
    button.addEventListener("click", () => runSystemAction(button.dataset.systemAction));
  });
  $("#settingsReloadJsonBtn")?.addEventListener("click", loadSettingsPage);
  $("#settingsChatModelSaveBtn")?.addEventListener("click", saveChatModel);
  $("#settingsEmbedRebuildBtn")?.addEventListener("click", rebuildEmbedModel);
  $("#settingsBehaviorSaveBtn")?.addEventListener("click", () => saveJsonConfig("settingsBehaviorJson", "behavior-rules"));
  $("#settingsAnswerSaveBtn")?.addEventListener("click", () => saveJsonConfig("settingsAnswerJson", "answer-styles"));
  $("#settingsQuotePolicySaveBtn")?.addEventListener("click", () => saveJsonConfig("settingsQuotePolicyJson", "quote-policies"));
  $("#settingsPricingSaveBtn")?.addEventListener("click", () => saveJsonConfig("settingsPricingJson", "quote-catalog"));

  document.addEventListener("click", (event) => {
    const exampleButton = event.target.closest("[data-config-example]");
    if (exampleButton) {
      const input = $("#configQuoteInput");
      if (input) {
        input.value = exampleButton.dataset.configExample || "";
        input.focus();
      }
      return;
    }

    const feedbackButton = event.target.closest("[data-config-feedback]");
    if (feedbackButton) {
      saveConfigQuoteFeedback(feedbackButton.dataset.configFeedback || "needs_review");
      return;
    }

    const answerFeedbackCase = event.target.closest("[data-feedback-to-case]");
    if (answerFeedbackCase) {
      event.preventDefault();
      feedbackToRegressionCase(answerFeedbackCase.dataset.feedbackToCase || "");
      return;
    }

    const docDelete = event.target.closest("[data-doc-delete]");
    if (docDelete) {
      event.preventDefault();
      deleteKnowledgeDoc(docDelete.dataset.docDelete || "");
      return;
    }

    const faqEdit = event.target.closest("[data-faq-edit]");
    if (faqEdit) {
      event.preventDefault();
      const item = state.faqs.find((row) => row.id === faqEdit.dataset.faqEdit);
      fillFaqForm(item || null);
      return;
    }

    const ruleEdit = event.target.closest("[data-rule-edit]");
    if (ruleEdit) {
      event.preventDefault();
      const item = state.rules.find((row) => row.id === ruleEdit.dataset.ruleEdit);
      fillRuleForm(item || null);
      return;
    }

    const memoryEdit = event.target.closest("[data-memory-edit]");
    if (memoryEdit) {
      event.preventDefault();
      const [channel, ...rest] = (memoryEdit.dataset.memoryEdit || "").split(":");
      const userId = rest.join(":");
      const item = state.memories.find((row) => row.channel === channel && row.user_id === userId);
      fillMemoryForm(item || null);
      return;
    }

    const learnedDelete = event.target.closest("[data-learned-delete]");
    if (learnedDelete) {
      event.preventDefault();
      deleteLearnedKnowledge(learnedDelete.dataset.learnedDelete || "");
    }
  });

  $("#knowledgeDocSearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchKnowledgeDocs();
  });
  $("#knowledgeLearnedSearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchLearnedKnowledge();
  });
  $("#knowledgeMemorySearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchKnowledgeMemories();
  });
  $("#salesArchiveSearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchQuoteArchives();
  });
  $("#memoryPageSearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchMemoryPage();
  });
}

async function loadCurrentPage() {
  try {
    if (state.page === "overview") await loadOverviewPage();
    else if (state.page === "quality") await loadQualityPage();
    else if (state.page === "regression") await loadRegressionPage();
    else if (state.page === "knowledge") await loadKnowledgePage();
    else if (state.page === "sales") await loadSalesPage();
    else if (state.page === "memory") await loadMemoryPage();
    else if (state.page === "training") await loadTrainingPage();
    else if (state.page === "diagnostics") await loadDiagnosticsPage();
    else if (state.page === "settings") await loadSettingsPage();
  } catch (e) {
    const section = document.querySelector(`.page-section[data-section="${state.page}"]`);
    if (section) {
      section.insertAdjacentHTML("afterbegin", `<div class="notice error">页面加载失败：${escapeHtml(e.message)}</div>`);
    }
  } finally {
    renderFooterStatus();
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  setPageShell();
  bindEvents();
  await loadCurrentPage();
});
