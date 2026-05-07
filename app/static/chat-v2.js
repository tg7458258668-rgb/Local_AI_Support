const chatBox = document.getElementById("chat-box");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const debugToggle = document.getElementById("debug-toggle");
const channelInput = document.getElementById("channel-input");
const userIdInput = document.getElementById("user-id-input");
const conversationIdInput = document.getElementById("conversation-id-input");
const memoryStatus = document.getElementById("memory-status");
const memorySummary = document.getElementById("memory-summary");
const refreshMemoryBtn = document.getElementById("refresh-memory-btn");

function escapeHtml(text) {
  if (text === null || text === undefined) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
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

  const paragraphs = safe
    .split(/\n\s*\n/)
    .map(p => p.trim())
    .filter(Boolean)
    .map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`);

  return paragraphs.join("") || "<p></p>";
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

function getTesterConfig() {
  return {
    channel: channelInput?.value || "api",
    user_id: userIdInput?.value.trim() || "",
    conversation_id: conversationIdInput?.value.trim() || ""
  };
}

function saveTesterConfig() {
  const config = getTesterConfig();
  localStorage.setItem("chat_test_channel", config.channel);
  localStorage.setItem("chat_test_user_id", config.user_id);
  localStorage.setItem("chat_test_conversation_id", config.conversation_id);
  updateMemoryStatus();
}

function loadTesterConfig() {
  if (channelInput) channelInput.value = localStorage.getItem("chat_test_channel") || "api";
  if (userIdInput) userIdInput.value = localStorage.getItem("chat_test_user_id") || "";
  if (conversationIdInput) conversationIdInput.value = localStorage.getItem("chat_test_conversation_id") || "";
  updateMemoryStatus();
}

function updateMemoryStatus() {
  if (!memoryStatus) return;
  const config = getTesterConfig();
  if (!config.user_id) {
    memoryStatus.textContent = "未填写客户 ID，不会写入长期记忆。";
    memoryStatus.className = "panel-subtitle muted";
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
    const resp = await fetch(`/api/admin/memories?q=${encodeURIComponent(config.user_id)}`);
    const data = await resp.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const item = items.find(x => x.channel === config.channel && x.user_id === config.user_id) || null;
    renderMemorySummary(item);
  } catch (err) {
    if (memorySummary) {
      memorySummary.className = "memory-summary empty error";
      memorySummary.textContent = `读取客户画像失败：${err}`;
    }
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
    <section class="debug-section">
      <div class="debug-title">${escapeHtml(title)}</div>
      <div class="debug-body">${html}</div>
    </section>
  `;
}

function buildKeyValueRows(rows) {
  return rows
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([label, value]) => `<div class="meta-row"><strong>${escapeHtml(label)}：</strong>${escapeHtml(value)}</div>`)
    .join("");
}

function buildMemoryDebug(memory) {
  const rows = memoryRows(memory);
  if (!rows.length) return `<div class="empty-debug">本轮没有客户记忆。填写客户 ID 后才会读写长期记忆。</div>`;
  return `<div class="debug-chip-list">${rows.map(([label, value]) => `
    <span class="debug-chip"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</span>
  `).join("")}</div>`;
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
      <div class="msg-text msg-loading">正在思考，请稍候...</div>
    </div>
  `;
  chatBox.appendChild(wrap);
  scrollToBottom();
}

function removeLoadingMessage() {
  const el = document.getElementById("loading-message");
  if (el) el.remove();
}

function appendAiMessage(data) {
  const answer = data.answer || data.response || "暂无回答";
  const route = data.route || "-";
  const matchedRule = formatMatchedRule(data.matched_rule);
  const faqScore = formatScore(data.faq_score ?? data.faq_top_score);
  const docScore = formatScore(data.doc_score ?? data.doc_top_score);
  const hint = formatHint(data);
  const elapsedText = formatElapsed(data.elapsed_ms ?? data.timings?.total_ms);
  const debugMode = getDebugMode();

  const rawSources = Array.isArray(data.sources) ? data.sources : [];
  const sources = dedupeSources(rawSources);
  const timingRows = buildTimingRows(data.timings);

  const routeHtml = buildKeyValueRows([
    ["路由", route],
    ["需要人工", data.need_human ? "是" : "否"],
    ["规则命中", matchedRule],
    ["FAQ分数", faqScore],
    ["DOC分数", docScore],
    ["提示", hint],
    ["渠道", data.channel],
    ["客户ID", data.user_id],
    ["会话ID", data.conversation_id]
  ]);
  const quoteHtml = buildQuoteDebug(data.metadata || {});
  const retrievalHtml = buildRetrievalDebug(data, sources);

  renderMemorySummary(data.memory || null);

  const wrap = document.createElement("div");
  wrap.className = "msg msg-ai";
  wrap.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-bubble">
      <div class="msg-text">${formatRichText(answer)}</div>
      <div class="elapsed-line"><strong>接口总耗时：</strong>${escapeHtml(elapsedText)}</div>
      <div class="msg-meta ${debugMode ? "" : "hidden"}">
        ${buildDebugSection("路由与决策", routeHtml)}
        ${buildDebugSection("客户记忆", buildMemoryDebug(data.memory))}
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

  appendUserMessage(question);
  questionInput.value = "";
  appendLoadingMessage();
  saveTesterConfig();
  const config = getTesterConfig();

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
          test_page: true
        }
      })
    });

    const data = await resp.json();
    console.log("chat response:", data);
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
      });
      return;
    }
    appendAiMessage(data);
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
    });
  }
}

function resetChat() {
  chatBox.innerHTML = `
    <div class="msg msg-ai">
      <div class="msg-avatar">AI</div>
      <div class="msg-bubble">
        <div class="msg-text">
          你好，我是本地 AI 客服助手。你可以直接问我产品、保修、售后等问题。
        </div>
      </div>
    </div>
  `;
  questionInput.value = "";
}

sendBtn.addEventListener("click", sendQuestion);
clearBtn.addEventListener("click", resetChat);
if (refreshMemoryBtn) refreshMemoryBtn.addEventListener("click", refreshCurrentMemory);

[channelInput, userIdInput, conversationIdInput].forEach((input) => {
  if (!input) return;
  input.addEventListener("change", () => {
    saveTesterConfig();
    refreshCurrentMemory();
  });
  input.addEventListener("input", () => {
    saveTesterConfig();
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
    document.querySelectorAll(".msg-meta").forEach(el => {
      if (debugToggle.checked) el.classList.remove("hidden");
      else el.classList.add("hidden");
    });
  });
}

loadTesterConfig();
refreshCurrentMemory();
