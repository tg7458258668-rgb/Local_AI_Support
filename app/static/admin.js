const pageTitle = document.getElementById("page-title");
const pageDesc = document.getElementById("page-desc");
const refreshAllBtn = document.getElementById("refreshAllBtn");

const pageMap = {
  dashboard: {
    title: "系统概览",
    desc: "查看系统状态、资料库状态和日志"
  },
  docs: {
    title: "知识库",
    desc: "查看当前文档片段、分类和内容"
  },
  faqs: {
    title: "FAQ",
    desc: "查看、筛选、新增、编辑、删除 FAQ"
  },
  rules: {
    title: "优先规则",
    desc: "查看、编辑、测试优先规则"
  },
  "quote-policies": {
    title: "报价规则",
    desc: "维护报价草案的价目、折扣边界和审批条件"
  },
  "quote-archives": {
    title: "报价档案",
    desc: "查看客户需求、报价草案、来源案例和跟进状态"
  },
  memories: {
    title: "客户记忆",
    desc: "查看、编辑、删除客户关键画像"
  },
  logs: {
    title: "系统日志",
    desc: "查看当前日志输出"
  }
};

const faqState = {
  items: [],
  filteredItems: [],
  selectedId: null,
  mode: "create",
  keyword: "",
  category: "",
  status: ""
};

const ruleState = {
  items: [],
  filteredItems: [],
  selectedId: null,
  mode: "create",
  keyword: ""
};

const categoryState = {
  items: [],
  target: "faq"
};

const docsState = {
  items: [],
  stats: new Map(),
  selected: new Set(),
  viewMode: "docs",
  expanded: new Set(),
  query: ""
};

const quotePolicyState = {
  policy: {},
  catalog: { products: [], accessories: [], updated_at: "" },
  approvalOptions: ["优惠价", "低于标价", "交付时间", "合同条款", "特殊定制"]
};

const LAUNCHER_BASE = "http://127.0.0.1:7999";

function safeText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function escapeHtml(text) {
  return safeText(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function methodLabel(method) {
  const labels = {
    pdf_text: "PDF文本",
    pdf_text_ocr: "PDF文本+OCR",
    preview_pdf_text: "Pages预览PDF",
    textutil: "Pages文本",
    pages_preview_ocr: "Pages OCR"
  };
  return labels[method] || method || "-";
}

function formatPriceFields(fields) {
  if (!fields || typeof fields !== "object") return "";
  return Object.entries(fields)
    .map(([key, value]) => `${key}=${value}`)
    .join("；");
}

function normalizePriority(value) {
  const n = Number(value || 1);
  if (Number.isNaN(n) || n < 1) return 1;
  return Math.floor(n);
}

function getFaqStatusText(status) {
  return status === "active" ? "已启用" : "未启动";
}

function getFaqStatusClass(status) {
  return status === "active" ? "faq-status-enabled" : "faq-status-disabled";
}

function getRuleStatusText(status) {
  return status === "active" ? "已启用" : "未启动";
}

function getRuleStatusClass(status) {
  return status === "active" ? "faq-status-enabled" : "faq-status-disabled";
}

function getRuleActionText(action) {
  const map = {
    faq_first: "优先 FAQ",
    manual_required: "必须转人工",
    doc_first: "优先文档",
    block_commitment: "禁止承诺"
  };
  return map[action] || "优先 FAQ";
}

function sortByPriorityAndId(items) {
  return [...items].sort((a, b) => {
    const pa = normalizePriority(a.priority);
    const pb = normalizePriority(b.priority);
    if (pa !== pb) return pa - pb;
    return safeText(a.id).localeCompare(safeText(b.id), "zh-CN");
  });
}

function setStatusBadge(el, value) {
  if (!el) return;
  const online = value === "online";
  el.textContent = online ? "在线" : "离线";
  el.className = "status-badge " + (online ? "green" : "red");
}

function updateOverallHealth() {
  const values = [
    document.getElementById("backendStatus")?.textContent,
    document.getElementById("ollamaStatus")?.textContent,
    document.getElementById("qdrantStatus")?.textContent
  ];
  const allOnline = values.every((value) => value === "在线");
  const healthOverallText = document.getElementById("healthOverallText");
  const healthOverallBadge = document.getElementById("healthOverallBadge");
  if (healthOverallText) healthOverallText.textContent = allOnline ? "全部服务正常" : "部分服务异常";
  if (healthOverallBadge) {
    healthOverallBadge.textContent = allOnline ? "健康" : "需检查";
    healthOverallBadge.className = "status-badge " + (allOnline ? "green" : "red");
  }
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
    throw new Error(data.detail || `请求失败：${url}`);
  }

  return data;
}

function switchTab(tab) {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.remove("active");
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.remove("active");
  });

  const navBtn = document.querySelector(`.nav-btn[data-tab="${tab}"]`);
  const panel = document.getElementById(`tab-${tab}`);

  if (navBtn) navBtn.classList.add("active");
  if (panel) panel.classList.add("active");

  if (pageTitle) pageTitle.textContent = pageMap[tab]?.title || "";
  if (pageDesc) pageDesc.textContent = pageMap[tab]?.desc || "";
}

function showResultModal(title, message) {
  const modal = document.getElementById("resultModal");
  const titleEl = document.getElementById("resultModalTitle");
  const bodyEl = document.getElementById("resultModalBody");
  if (!modal || !titleEl || !bodyEl) {
    alert(`${title}\n\n${message}`);
    return;
  }

  titleEl.textContent = title;
  bodyEl.innerHTML = `<div class="result-message">${escapeHtml(message).replace(/\n/g, "<br>")}</div>`;
  modal.classList.remove("hidden");
}

function hideResultModal() {
  const modal = document.getElementById("resultModal");
  if (modal) modal.classList.add("hidden");
}

function showActionNotice(targetId, message, type = "success", options = {}) {
  const el = document.getElementById(targetId);
  if (!el) return;

  el.textContent = message;
  el.className = `action-notice ${type}`;
  el.classList.remove("hidden");

  clearTimeout(el.__timer);
  if (options.sticky) return;
  el.__timer = setTimeout(() => {
    el.classList.add("hidden");
  }, options.duration || 2500);
}

function formatSelectedDocFiles(files) {
  if (!files.length) return "尚未选择文件";
  const names = files.map((file) => `- ${file.name}`).join("\n");
  return `已选择 ${files.length} 个文件\n${names}`;
}

function updateDocUploadSelection() {
  const fileInput = document.getElementById("docUploadFile");
  const selection = document.getElementById("docUploadSelection");
  const pickerTitle = document.getElementById("docFilePickerTitle");
  const pickerHint = document.getElementById("docFilePickerHint");
  if (!selection) return;
  const files = Array.from(fileInput?.files || []);
  if (!files.length) {
    selection.textContent = "";
    selection.classList.add("hidden");
    if (pickerTitle) pickerTitle.textContent = "选择知识库文件";
    if (pickerHint) pickerHint.textContent = "支持 txt、md、docx、pdf、pages；可多选";
    return;
  }
  selection.textContent = formatSelectedDocFiles(files);
  selection.classList.remove("hidden");
  if (pickerTitle) pickerTitle.textContent = `已选择 ${files.length} 个文件`;
  if (pickerHint) {
    const names = files.map((file) => file.name).slice(0, 3).join("、");
    pickerHint.textContent = files.length > 3 ? `${names} 等 ${files.length} 个文件` : names;
  }
}

function formatReindexText(reindex) {
  if (!reindex) return "未返回入库结果";
  const faqCount = safeText(reindex.faq_count || 0);
  const pointCount = safeText(reindex.point_count || 0);
  const collection = safeText(reindex.collection || "-");
  return `FAQ 入库成功：${faqCount} 条 FAQ，${pointCount} 条向量，集合：${collection}`;
}

function normalizeRuleKeywords(raw) {
  if (Array.isArray(raw)) {
    return raw.map((x) => safeText(x).trim()).filter(Boolean);
  }

  const text = safeText(raw).trim();
  if (!text) return [];

  if (text.includes("|")) {
    return text.split("|").map((x) => x.trim()).filter(Boolean);
  }

  if (text.startsWith("[") && text.endsWith("]")) {
    try {
      const normalized = text.replace(/'/g, '"');
      const parsed = JSON.parse(normalized);
      if (Array.isArray(parsed)) {
        return parsed.map((x) => safeText(x).trim()).filter(Boolean);
      }
    } catch (e) {
      const cleaned = text
        .replace(/^\[/, "")
        .replace(/\]$/, "")
        .split(",")
        .map((x) => x.replace(/['"]/g, "").trim())
        .filter(Boolean);

      if (cleaned.length) return cleaned;
    }
  }

  return [text];
}

function closeAllPopovers() {
  const faqSearchPopover = document.getElementById("faqSearchPopover");
  const ruleSearchPopover = document.getElementById("ruleSearchPopover");

  if (faqSearchPopover) faqSearchPopover.classList.add("hidden");
  if (ruleSearchPopover) ruleSearchPopover.classList.add("hidden");
}

async function loadStatus() {
  try {
    const data = await fetchJson("/api/admin/status");
    setStatusBadge(document.getElementById("backendStatus"), data.backend);
    setStatusBadge(document.getElementById("ollamaStatus"), data.ollama);
    setStatusBadge(document.getElementById("qdrantStatus"), data.qdrant);
    const backendBaseDir = document.getElementById("backendBaseDir");
    if (backendBaseDir) backendBaseDir.textContent = data.base_dir || "-";
    updateOverallHealth();
  } catch (e) {
    console.error(e);
    updateOverallHealth();
  }
}

async function fetchLauncher(path, options = {}) {
  const url = path.startsWith("/api/system") ? path : `${LAUNCHER_BASE}${path}`;
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`系统控制请求失败：${res.status}`);
  return await res.json();
}

function setLauncherBadge(online) {
  const launcherStatus = document.getElementById("launcherStatus");
  if (!launcherStatus) return;
  launcherStatus.textContent = online ? "可用" : "未启动";
  launcherStatus.className = "status-badge " + (online ? "green" : "red");
}

async function loadServiceControlStatus() {
  const serviceRunningStatus = document.getElementById("serviceRunningStatus");
  const servicePidText = document.getElementById("servicePidText");
  const qdrantRunningStatus = document.getElementById("qdrantRunningStatus");
  const qdrantModeText = document.getElementById("qdrantModeText");
  const launcherBaseDirText = document.getElementById("launcherBaseDirText");
  const serviceControlMessage = document.getElementById("serviceControlMessage");

  try {
    const data = await fetchLauncher("/api/system/status");
    const app = data.app || data;
    const qdrant = data.qdrant || {};
    setLauncherBadge(true);
    if (serviceRunningStatus) {
      serviceRunningStatus.textContent = app.running ? "运行中" : "未运行";
      serviceRunningStatus.className = "status-badge " + (app.running ? "green" : "red");
    }
    if (servicePidText) servicePidText.textContent = app.pid || "-";
    if (qdrantRunningStatus) {
      qdrantRunningStatus.textContent = qdrant.running ? "运行中" : "未运行";
      qdrantRunningStatus.className = "status-badge " + (qdrant.running ? "green" : "red");
    }
    if (qdrantModeText) qdrantModeText.textContent = qdrant.mode || "-";
    if (launcherBaseDirText) launcherBaseDirText.textContent = data.base_dir || app.base_dir || "-";
    if (serviceControlMessage) {
      const qdrantTip = qdrant.availability_message ? `；Qdrant：${qdrant.availability_message}` : "";
      const dockerTip = qdrant.docker_path ? `；Docker：${qdrant.docker_path}（${qdrant.docker_ready ? "已就绪" : (qdrant.docker_error || "未就绪")}）` : "";
      const baseDirTip = data.base_dir ? `；目录：${data.base_dir}` : "";
      serviceControlMessage.textContent = data.message || `业务地址：${app.url || "-"}；向量库地址：${qdrant.url || "-"}${qdrantTip}${dockerTip}${baseDirTip}`;
    }
  } catch (e) {
    setLauncherBadge(false);
    if (serviceRunningStatus) {
      serviceRunningStatus.textContent = "当前页面在线";
      serviceRunningStatus.className = "status-badge green";
    }
    if (servicePidText) servicePidText.textContent = "-";
    if (qdrantRunningStatus) {
      qdrantRunningStatus.textContent = "未知";
      qdrantRunningStatus.className = "status-badge gray";
    }
    if (qdrantModeText) qdrantModeText.textContent = "-";
    if (launcherBaseDirText) launcherBaseDirText.textContent = "-";
    if (serviceControlMessage) {
      serviceControlMessage.textContent = "启动器未运行。需要未启动时也能控制系统，请打开“本地 AI 客服启动器”，或运行 python support_launcher.py。";
    }
  }
}

async function runServiceAction(action) {
  const serviceControlMessage = document.getElementById("serviceControlMessage");
  try {
    const data = await fetchLauncher(`/api/system/${action}`, { method: "POST" });
    if (serviceControlMessage) serviceControlMessage.textContent = data.message || "操作已发送";
    setTimeout(loadServiceControlStatus, 800);
  } catch (e) {
    if (serviceControlMessage) {
      serviceControlMessage.textContent = "操作失败：启动器未运行。请先打开“本地 AI 客服启动器”。";
    }
  }
}

async function loadSummary() {
  try {
    const data = await fetchJson("/api/admin/summary");
    const docCount = document.getElementById("docCount");
    const chunkCount = document.getElementById("chunkCount");
    const faqCount = document.getElementById("faqCount");
    const ruleCount = document.getElementById("ruleCount");
    const docNameList = document.getElementById("docNameList");

    if (docCount) docCount.textContent = safeText(data.doc_count || 0);
    if (chunkCount) chunkCount.textContent = safeText(data.doc_chunk_count || 0);
    if (faqCount) faqCount.textContent = safeText(data.faq_count || 0);
    if (ruleCount) ruleCount.textContent = safeText(data.rule_count || 0);

    if (docNameList) {
      docNameList.innerHTML = "";
      const names = Array.isArray(data.doc_names) ? data.doc_names : [];
      if (!names.length) {
        docNameList.innerHTML = `<div class="tag">暂无文档</div>`;
      } else {
        names.forEach((name) => {
          const tag = document.createElement("div");
          tag.className = "tag";
          tag.textContent = name;
          docNameList.appendChild(tag);
        });
      }
    }
  } catch (e) {
    console.error(e);
  }
}

async function loadDocs(q = "") {
  try {
    const data = await fetchJson(`/api/admin/docs?q=${encodeURIComponent(q)}`);
    const docsCount = document.getElementById("docsCount");
    docsState.query = q;
    docsState.items = Array.isArray(data.items) ? data.items : [];
    docsState.selected.clear();
    docsState.expanded.clear();
    buildDocStats(docsState.items);

    if (docsCount) {
      const docCount = docsState.stats.size;
      const chunkCount = data.total || docsState.items.length;
      const prefix = q ? "搜索结果：" : "";
      docsCount.textContent = `${prefix}共 ${docCount} 个文档，${chunkCount} 个片段；当前展示前 ${Math.min(chunkCount, 200)} 个片段`;
    }
    renderDocsTable();
    updateDocSelectionInfo();
  } catch (e) {
    console.error(e);
    showResultModal("加载失败", `加载知识库失败：${e.message}`);
  }
}

function buildDocStats(items) {
  docsState.stats = new Map();
  items.forEach((item) => {
    const name = item.doc_name || "";
    if (!name) return;
    const current = docsState.stats.get(name) || {
      doc_name: name,
      count: 0,
      sources: new Set(),
      categories: new Set(),
      methods: new Set(),
      docTypes: new Set(),
      priceFields: {},
      quoteItems: [],
      updated_at: "",
      items: [],
    };
    current.count += 1;
    current.items.push(item);
    if (item.source) current.sources.add(item.source);
    if (item.category) current.categories.add(item.category);
    if (item.extraction_method) current.methods.add(methodLabel(item.extraction_method));
    if (item.doc_type) current.docTypes.add(item.doc_type);
    if (item.updated_at && item.updated_at > current.updated_at) current.updated_at = item.updated_at;
    if (item.price_fields && typeof item.price_fields === "object") {
      current.priceFields = { ...current.priceFields, ...item.price_fields };
    }
    if (Array.isArray(item.quote_items) && item.quote_items.length) {
      current.quoteItems.push(...item.quote_items.slice(0, 5));
    }
    docsState.stats.set(name, current);
  });
}

function renderDocsTable() {
  const tbody = document.getElementById("docsTableBody");
  renderDocsTableHead();
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!docsState.items.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">没有找到知识库内容</td></tr>`;
    syncDocCheckboxes();
    return;
  }
  if (docsState.viewMode === "chunks") {
    renderChunkRows(tbody, docsState.items);
  } else {
    renderDocumentRows(tbody);
  }
  syncDocCheckboxes();
}

function renderDocsTableHead() {
  const head = document.getElementById("docsTableHead");
  const table = document.querySelector(".docs-table");
  if (!head || !table) return;
  table.classList.toggle("docs-table-doc-view", docsState.viewMode === "docs");
  table.classList.toggle("docs-table-chunk-view", docsState.viewMode === "chunks");
  if (docsState.viewMode === "chunks") {
    head.innerHTML = `
      <tr>
        <th>选择</th>
        <th>ID</th>
        <th>文档</th>
        <th>章节</th>
        <th>分类</th>
        <th>解析</th>
        <th>内容</th>
        <th>操作</th>
      </tr>
    `;
    return;
  }
  head.innerHTML = `
    <tr>
      <th>选择</th>
      <th>文档</th>
      <th>原文件</th>
      <th>分类</th>
      <th>解析</th>
      <th>片段</th>
      <th>摘要</th>
      <th>操作</th>
    </tr>
  `;
}

function renderChunkRows(tbody, items) {
  items.forEach((item) => {
    const docName = item.doc_name || "";
    const stats = docsState.stats.get(docName) || { count: 1, sources: new Set() };
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${docName ? `<input type="checkbox" class="doc-select-checkbox" data-doc-name="${escapeHtml(docName)}" />` : ""}</td>
      <td>${escapeHtml(item.id || "")}</td>
      <td>${escapeHtml(docName)}</td>
      <td>${escapeHtml(item.section || "")}</td>
      <td>${escapeHtml(item.category || "")}</td>
      <td>
        <div>${escapeHtml(methodLabel(item.extraction_method || ""))}</div>
        <div class="small">${escapeHtml(item.doc_type || "")}</div>
      </td>
      <td>
        <div>${escapeHtml(item.text || "")}</div>
        <div class="small">来源：${escapeHtml(item.source || "")}</div>
        ${item.price_fields ? `<div class="small">价格：${escapeHtml(formatPriceFields(item.price_fields))}</div>` : ""}
      </td>
      <td>${docName ? `<button type="button" class="danger-btn doc-delete-btn">删除</button>` : ""}</td>
    `;
    bindDocRowActions(tr, docName, stats);
    tbody.appendChild(tr);
  });
}

function renderDocumentRows(tbody) {
  Array.from(docsState.stats.values()).forEach((doc) => {
    const tr = document.createElement("tr");
    tr.className = "doc-summary-row";
    const sources = Array.from(doc.sources);
    const matchedText = docsState.query ? `<span class="doc-pill">命中 ${doc.count} 个片段</span>` : "";
    const priceText = formatPriceFields(doc.priceFields);
    const quoteText = doc.quoteItems.length ? `配置：${doc.quoteItems.slice(0, 4).join("；")}` : "";
    tr.innerHTML = `
      <td><input type="checkbox" class="doc-select-checkbox" data-doc-name="${escapeHtml(doc.doc_name)}" /></td>
      <td>
        <strong>${escapeHtml(doc.doc_name)}</strong>
        <div class="small">更新时间：${escapeHtml(doc.updated_at || "-")}</div>
      </td>
      <td>${escapeHtml(sources.join("、") || "-")}</td>
      <td>${escapeHtml(Array.from(doc.categories).join("、") || "-")}</td>
      <td>
        <div>${escapeHtml(Array.from(doc.methods).join("、") || "-")}</div>
        <div class="small">${escapeHtml(Array.from(doc.docTypes).join("、") || "")}</div>
      </td>
      <td>
        <span class="doc-pill">${doc.count} 个片段</span>
        ${matchedText}
      </td>
      <td>
        ${priceText ? `<div class="small">价格：${escapeHtml(priceText)}</div>` : ""}
        ${quoteText ? `<div class="small">${escapeHtml(quoteText)}</div>` : ""}
        ${!priceText && !quoteText ? `<div class="small">${escapeHtml((doc.items[0]?.text || "").slice(0, 120))}</div>` : ""}
      </td>
      <td>
        <div class="doc-action-stack">
          <button type="button" class="ghost-btn doc-expand-btn">${docsState.expanded.has(doc.doc_name) ? "收起片段" : "展开片段"}</button>
          <button type="button" class="danger-btn doc-delete-btn">删除</button>
        </div>
      </td>
    `;
    bindDocRowActions(tr, doc.doc_name, doc);
    tr.querySelector(".doc-expand-btn")?.addEventListener("click", () => toggleDocExpanded(doc.doc_name));
    tbody.appendChild(tr);
    if (docsState.expanded.has(doc.doc_name)) {
      tbody.appendChild(renderDocDetailsRow(doc));
    }
  });
}

function renderDocDetailsRow(doc) {
  const tr = document.createElement("tr");
  tr.className = "doc-detail-row";
  const rows = doc.items.map((item, index) => `
    <div class="doc-chunk-card">
      <div class="doc-chunk-title">片段 ${index + 1} ｜ ${escapeHtml(item.section || "全文")}</div>
      <div class="doc-chunk-text">${escapeHtml(item.text || "")}</div>
      <div class="doc-chunk-meta">
        来源：${escapeHtml(item.source || "-")} ｜ 分类：${escapeHtml(item.category || "-")} ｜ 解析：${escapeHtml(methodLabel(item.extraction_method || ""))}
        ${item.price_fields ? ` ｜ 价格：${escapeHtml(formatPriceFields(item.price_fields))}` : ""}
      </div>
    </div>
  `).join("");
  tr.innerHTML = `<td colspan="8"><div class="doc-detail-panel">${rows}</div></td>`;
  return tr;
}

function bindDocRowActions(row, docName, stats) {
  row.querySelector(".doc-delete-btn")?.addEventListener("click", () => {
    deleteDoc(docName, stats.count, Array.from(stats.sources || []));
  });
  row.querySelector(".doc-select-checkbox")?.addEventListener("change", (e) => {
    toggleDocSelection(docName, e.target.checked);
  });
}

function toggleDocExpanded(docName) {
  if (docsState.expanded.has(docName)) docsState.expanded.delete(docName);
  else docsState.expanded.add(docName);
  renderDocsTable();
}

function setDocsViewMode(mode) {
  docsState.viewMode = mode === "chunks" ? "chunks" : "docs";
  document.getElementById("docViewModeBtn")?.classList.toggle("active", docsState.viewMode === "docs");
  document.getElementById("chunkViewModeBtn")?.classList.toggle("active", docsState.viewMode === "chunks");
  renderDocsTable();
}

function refreshDocsViewModeButtons() {
  document.getElementById("docViewModeBtn")?.classList.toggle("active", docsState.viewMode === "docs");
  document.getElementById("chunkViewModeBtn")?.classList.toggle("active", docsState.viewMode === "chunks");
}

function toggleDocSelection(docName, selected) {
  if (!docName) return;
  if (selected) docsState.selected.add(docName);
  else docsState.selected.delete(docName);
  syncDocCheckboxes();
  updateDocSelectionInfo();
}

function syncDocCheckboxes() {
  document.querySelectorAll(".doc-select-checkbox").forEach((input) => {
    const docName = input.dataset.docName || "";
    input.checked = docsState.selected.has(docName);
  });
  const allBox = document.getElementById("docSelectAll");
  if (allBox) {
    const allNames = Array.from(docsState.stats.keys());
    allBox.checked = allNames.length > 0 && allNames.every((name) => docsState.selected.has(name));
    allBox.indeterminate = !allBox.checked && allNames.some((name) => docsState.selected.has(name));
  }
}

function updateDocSelectionInfo() {
  const info = document.getElementById("docSelectionInfo");
  const deleteBtn = document.getElementById("docBatchDeleteBtn");
  const names = Array.from(docsState.selected);
  if (info) {
    info.textContent = names.length
      ? `已选择 ${names.length} 个文档：${names.slice(0, 5).join("、")}${names.length > 5 ? "..." : ""}`
      : "未选择文档";
  }
  if (deleteBtn) deleteBtn.disabled = names.length === 0;
}

function setAllVisibleDocsSelected(selected) {
  docsState.selected.clear();
  if (selected) {
    Array.from(docsState.stats.keys()).forEach((name) => docsState.selected.add(name));
  }
  syncDocCheckboxes();
  updateDocSelectionInfo();
}

async function deleteDoc(docName, chunkCount = 0, sources = []) {
  const sourceText = sources.length ? `\n原文件：${sources.join("、")}` : "";
  const ok = confirm(`确认删除知识库文档？\n\n文档：${docName}\n片段：${chunkCount} 条${sourceText}\n\n删除后会同步重建文档向量库。`);
  if (!ok) return;
  showActionNotice("docUploadNotice", `正在删除文档：${docName}，并重建文档向量库...`, "loading", { sticky: true });
  try {
    const data = await fetchJson(`/api/admin/docs/${encodeURIComponent(docName)}`, { method: "DELETE" });
    showActionNotice(
      "docUploadNotice",
      `已删除文档：${data.deleted_doc_name || docName}\n删除片段：${data.deleted_chunk_count || 0} 条\n剩余片段：${data.remaining_chunk_count || 0} 条`,
      "success",
      { sticky: true }
    );
    await loadDocs(document.getElementById("docSearchInput")?.value?.trim() || "");
    await loadSummary();
  } catch (e) {
    showActionNotice("docUploadNotice", `删除失败：${e.message}`, "error", { sticky: true });
  }
}

async function batchDeleteDocs() {
  const names = Array.from(docsState.selected);
  if (!names.length) {
    showActionNotice("docUploadNotice", "请先选择要删除的知识库文档", "error");
    return;
  }
  const totalChunks = names.reduce((sum, name) => sum + (docsState.stats.get(name)?.count || 0), 0);
  const ok = confirm(`确认批量删除知识库文档？\n\n文档数：${names.length} 个\n片段数：${totalChunks} 条\n\n${names.join("\n")}\n\n删除后会重建文档向量库，请耐心等待。`);
  if (!ok) return;

  showActionNotice("docUploadNotice", `正在批量删除 ${names.length} 个文档...`, "loading", { sticky: true });
  try {
    const data = await fetchJson("/api/admin/docs/delete-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_names: names })
    });
    const deleted = Array.isArray(data.deleted_doc_names) ? data.deleted_doc_names : names;
    const missing = Array.isArray(data.missing_doc_names) ? data.missing_doc_names : [];
    const missingText = missing.length ? `\n未找到：${missing.join("、")}` : "";
    showActionNotice(
      "docUploadNotice",
      `批量删除完成：删除 ${deleted.length} 个文档，${data.deleted_chunk_count || 0} 条片段。\n剩余片段：${data.remaining_chunk_count || 0} 条。${missingText}`,
      missing.length ? "error" : "success",
      { sticky: true }
    );
    docsState.selected.clear();
    await loadDocs(document.getElementById("docSearchInput")?.value?.trim() || "");
    await loadSummary();
  } catch (e) {
    showActionNotice("docUploadNotice", `批量删除失败：${e.message}`, "error", { sticky: true });
  }
}

async function uploadDocFile() {
  const fileInput = document.getElementById("docUploadFile");
  const nameInput = document.getElementById("docUploadName");
  const categoryInput = document.getElementById("docUploadCategory");
  const uploadBtn = document.getElementById("docUploadBtn");
  const notice = document.getElementById("docUploadNotice");
  const files = Array.from(fileInput?.files || []);

  if (!files.length) {
    showActionNotice("docUploadNotice", "请至少选择一个文件", "error");
    return;
  }

  const formData = new FormData();
  files.forEach((file) => formData.append("file", file));
  formData.append("doc_name", nameInput?.value?.trim() || "");
  formData.append("category", categoryInput?.value?.trim() || "");

  if (uploadBtn) uploadBtn.disabled = true;
  if (notice) {
    const names = files.map((file) => file.name).join("、");
    notice.textContent = `正在上传 ${files.length} 个文件，随后会解析、切块并写入知识库。\n${names}`;
    notice.className = "action-notice loading";
    notice.classList.remove("hidden");
    clearTimeout(notice.__timer);
  }

  try {
    const res = await fetch("/api/admin/docs/upload", {
      method: "POST",
      body: formData
    });
    let data = {};
    try {
      data = await res.json();
    } catch (e) {
      data = {};
    }
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${data.detail || "上传失败"}`);
    }

    const message = data.message || "上传完成";
    if (Array.isArray(data.results)) {
      const details = data.results.map((item) => {
        const name = item.source_file || item.doc_name || "-";
        const state = item.indexed ? "已入库" : (item.ok ? "已保存" : "失败");
        const method = item.extraction_method ? `，${methodLabel(item.extraction_method)}` : "";
        const chars = item.text_char_count ? `，${item.text_char_count} 字` : "";
        return `${name}：${state}${method}${chars}，片段 ${item.chunk_count || 0}${item.message ? `（${item.message}）` : ""}`;
      }).join("\n");
      showActionNotice("docUploadNotice", `${message}\n${details}`, data.failed_count ? "error" : "success", { sticky: true });
    } else {
      showActionNotice("docUploadNotice", `${message} 文档：${data.doc_name || "-"}，片段：${data.chunk_count || 0}`, data.ok === false ? "error" : "success", { sticky: true });
    }
    if (fileInput) fileInput.value = "";
    updateDocUploadSelection();
    await loadSummary();
    await loadDocs(document.getElementById("docSearchInput")?.value?.trim() || "");
    await loadLogs();
  } catch (e) {
    const names = files.map((file) => file.name).join("、");
    showActionNotice("docUploadNotice", `上传失败：${e.message}\n文件：${names}`, "error", { sticky: true });
  } finally {
    if (uploadBtn) uploadBtn.disabled = false;
  }
}

async function loadLogs() {
  const logBox = document.getElementById("logBox");
  const dashboardLog = document.getElementById("dashboardLog");

  try {
    const res = await fetch("/api/admin/logs");
    if (!res.ok) {
      const msg = "日志接口未启用，先不用管这个，不影响 FAQ 和规则管理。";
      if (logBox) logBox.textContent = msg;
      if (dashboardLog) dashboardLog.textContent = msg;
      return;
    }

    let data = {};
    try {
      data = await res.json();
    } catch (e) {
      data = {};
    }

    const text = safeText(data.text || "暂无日志");
    if (logBox) logBox.textContent = text;
    if (dashboardLog) dashboardLog.textContent = text;
  } catch (e) {
    console.error(e);
    const msg = "日志读取失败";
    if (logBox) logBox.textContent = msg;
    if (dashboardLog) dashboardLog.textContent = msg;
  }
}

function joinMemoryList(values) {
  return Array.isArray(values) && values.length ? values.join("、") : "-";
}

async function loadQuotePolicies() {
  try {
    const policy = await fetchJson("/api/admin/quote-policies");
    const catalog = await fetchJson("/api/admin/pricing-catalog");
    quotePolicyState.policy = policy || {};
    quotePolicyState.catalog = normalizePricingCatalog(catalog);
    renderQuotePolicyForm(quotePolicyState.policy);
    renderPricingCatalog(quotePolicyState.catalog);
    syncQuoteJsonFromForms(false);
  } catch (e) {
    console.error(e);
    showActionNotice("quotePolicyNotice", `报价规则加载失败：${e.message}`, "error", { sticky: true });
  }
}

function normalizePricingCatalog(catalog) {
  const source = catalog && typeof catalog === "object" ? catalog : {};
  return {
    products: Array.isArray(source.products) ? source.products : [],
    accessories: Array.isArray(source.accessories) ? source.accessories : [],
    updated_at: source.updated_at || ""
  };
}

function setInputValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value === null || value === undefined ? "" : String(value);
}

function renderQuotePolicyForm(policy) {
  setInputValue("quoteModeInput", policy.mode || "draft_only");
  setInputValue("quoteDefaultInput", policy.default_when_unconfigured || "list_price_only");
  setInputValue("quoteMaxDiscountInput", policy.max_discount_percent ?? "");
  setInputValue("quoteReplyStyleInput", policy.reply_style || "sales_talk");
  setInputValue("quoteMinMarginInput", policy.min_margin_note || "");
  setInputValue("quoteTemplateInput", policy.template || "");
  renderApprovalChecks(policy.approval_required || []);
}

function renderApprovalChecks(selectedValues) {
  const box = document.getElementById("quoteApprovalChecks");
  if (!box) return;
  const selected = new Set(Array.isArray(selectedValues) ? selectedValues : []);
  box.innerHTML = quotePolicyState.approvalOptions.map((item) => `
    <label class="check-item">
      <input type="checkbox" value="${escapeHtml(item)}" ${selected.has(item) ? "checked" : ""} />
      <span>${escapeHtml(item)}</span>
    </label>
  `).join("");
}

function collectQuotePolicyForm() {
  const checked = Array.from(document.querySelectorAll("#quoteApprovalChecks input:checked"))
    .map((input) => input.value);
  const discountRaw = document.getElementById("quoteMaxDiscountInput")?.value || "";
  const discount = discountRaw === "" ? "" : Number(discountRaw);
  return {
    mode: document.getElementById("quoteModeInput")?.value || "draft_only",
    default_when_unconfigured: document.getElementById("quoteDefaultInput")?.value || "list_price_only",
    max_discount_percent: Number.isFinite(discount) ? discount : "",
    min_margin_note: document.getElementById("quoteMinMarginInput")?.value.trim() || "",
    approval_required: checked,
    reply_style: document.getElementById("quoteReplyStyleInput")?.value || "sales_talk",
    template: document.getElementById("quoteTemplateInput")?.value.trim() || ""
  };
}

function updatePricingCatalogCount(catalog) {
  const catalogCount = document.getElementById("pricingCatalogCount");
  if (!catalogCount) return;
  const updated = catalog.updated_at ? ` ｜ 更新时间：${catalog.updated_at}` : "";
  catalogCount.textContent = `产品 ${catalog.products.length} 条，配件 ${catalog.accessories.length} 条${updated}`;
}

function priceInputValue(value) {
  return value === null || value === undefined ? "" : String(value);
}

function renderPricingCatalog(catalog) {
  const normalized = normalizePricingCatalog(catalog);
  const productBody = document.getElementById("pricingProductsBody");
  const accessoryBody = document.getElementById("pricingAccessoriesBody");
  if (productBody) {
    productBody.innerHTML = normalized.products.length
      ? normalized.products.map((item, index) => renderPricingProductRow(item, index)).join("")
      : `<tr><td colspan="7" class="empty-cell">暂无产品价目。可以新增产品，或从知识库生成草稿。</td></tr>`;
    bindPricingTableButtons(productBody);
  }
  if (accessoryBody) {
    accessoryBody.innerHTML = normalized.accessories.length
      ? normalized.accessories.map((item, index) => renderPricingAccessoryRow(item, index)).join("")
      : `<tr><td colspan="5" class="empty-cell">暂无配件价目。</td></tr>`;
    bindPricingTableButtons(accessoryBody);
  }
  updatePricingCatalogCount(normalized);
}

function renderPricingProductRow(item, index) {
  const configText = Array.isArray(item.configuration) ? item.configuration.join("\n") : safeText(item.configuration);
  return `
    <tr data-row-type="product" data-index="${index}">
      <td><input class="quote-table-input" data-field="product" value="${escapeHtml(item.product || "")}" placeholder="U-MOCO MINI" /></td>
      <td><input class="quote-table-input" data-field="version" value="${escapeHtml(item.version || "")}" placeholder="标准版" /></td>
      <td><input class="quote-table-input" data-field="base_price" value="${escapeHtml(priceInputValue(item.base_price))}" placeholder="¥300,000" /></td>
      <td><input class="quote-table-input" data-field="historical_offer" value="${escapeHtml(priceInputValue(item.historical_offer))}" placeholder="需人工确认" /></td>
      <td>
        <input class="quote-table-input source-input" data-field="source" value="${escapeHtml(item.source || "")}" readonly />
        <input type="hidden" data-field="doc_name" value="${escapeHtml(item.doc_name || "")}" />
      </td>
      <td><textarea class="quote-table-textarea" data-field="configuration" placeholder="一行一个配置项">${escapeHtml(configText)}</textarea></td>
      <td><button type="button" class="danger-btn small-btn pricing-delete-product" data-index="${index}">删除</button></td>
    </tr>
  `;
}

function renderPricingAccessoryRow(item, index) {
  return `
    <tr data-row-type="accessory" data-index="${index}">
      <td><input class="quote-table-input" data-field="name" value="${escapeHtml(item.name || "")}" placeholder="影视地面轨道" /></td>
      <td><input class="quote-table-input" data-field="unit" value="${escapeHtml(item.unit || "")}" placeholder="米 / 套" /></td>
      <td><input class="quote-table-input" data-field="reference_price" value="${escapeHtml(priceInputValue(item.reference_price))}" placeholder="¥15,000" /></td>
      <td><input class="quote-table-input" data-field="source" value="${escapeHtml(item.source || "")}" placeholder="人工维护" /></td>
      <td><button type="button" class="danger-btn small-btn pricing-delete-accessory" data-index="${index}">删除</button></td>
    </tr>
  `;
}

function bindPricingTableButtons(scope) {
  scope.querySelectorAll(".pricing-delete-product").forEach((btn) => {
    btn.addEventListener("click", () => deletePricingProduct(Number(btn.dataset.index)));
  });
  scope.querySelectorAll(".pricing-delete-accessory").forEach((btn) => {
    btn.addEventListener("click", () => deletePricingAccessory(Number(btn.dataset.index)));
  });
}

function collectPricingCatalogForm(touchUpdatedAt = false) {
  const products = Array.from(document.querySelectorAll('#pricingProductsBody tr[data-row-type="product"]')).map((row) => {
    const value = (field) => row.querySelector(`[data-field="${field}"]`)?.value.trim() || "";
    const configuration = value("configuration")
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
    return {
      product: value("product"),
      version: value("version"),
      base_price: value("base_price"),
      historical_offer: value("historical_offer"),
      source: value("source"),
      doc_name: value("doc_name"),
      configuration
    };
  }).filter((item) => item.product || item.version || item.base_price || item.configuration.length);

  const accessories = Array.from(document.querySelectorAll('#pricingAccessoriesBody tr[data-row-type="accessory"]')).map((row) => {
    const value = (field) => row.querySelector(`[data-field="${field}"]`)?.value.trim() || "";
    return {
      name: value("name"),
      unit: value("unit"),
      reference_price: value("reference_price"),
      source: value("source")
    };
  }).filter((item) => item.name || item.reference_price);

  return {
    products,
    accessories,
    updated_at: touchUpdatedAt
      ? new Date().toLocaleString("zh-CN", { hour12: false })
      : (quotePolicyState.catalog.updated_at || "")
  };
}

function addPricingProduct() {
  quotePolicyState.catalog = collectPricingCatalogForm();
  quotePolicyState.catalog.products.push({
    product: "",
    version: "",
    base_price: "",
    historical_offer: "",
    source: "",
    doc_name: "",
    configuration: []
  });
  renderPricingCatalog(quotePolicyState.catalog);
  syncQuoteJsonFromForms(false);
}

function deletePricingProduct(index) {
  quotePolicyState.catalog = collectPricingCatalogForm();
  quotePolicyState.catalog.products.splice(index, 1);
  renderPricingCatalog(quotePolicyState.catalog);
  syncQuoteJsonFromForms(false);
}

function addPricingAccessory() {
  quotePolicyState.catalog = collectPricingCatalogForm();
  quotePolicyState.catalog.accessories.push({
    name: "",
    unit: "",
    reference_price: "",
    source: "人工维护"
  });
  renderPricingCatalog(quotePolicyState.catalog);
  syncQuoteJsonFromForms(false);
}

function deletePricingAccessory(index) {
  quotePolicyState.catalog = collectPricingCatalogForm();
  quotePolicyState.catalog.accessories.splice(index, 1);
  renderPricingCatalog(quotePolicyState.catalog);
  syncQuoteJsonFromForms(false);
}

function syncQuoteJsonFromForms(showNotice = true) {
  quotePolicyState.policy = collectQuotePolicyForm();
  quotePolicyState.catalog = collectPricingCatalogForm();
  const policyEl = document.getElementById("quotePolicyJson");
  const catalogEl = document.getElementById("pricingCatalogJson");
  if (policyEl) policyEl.value = JSON.stringify(quotePolicyState.policy, null, 2);
  if (catalogEl) catalogEl.value = JSON.stringify(quotePolicyState.catalog, null, 2);
  if (showNotice) {
    showActionNotice("quoteJsonNotice", "已把当前表单同步到 JSON。", "success", { sticky: true });
  }
}

function toggleQuoteJsonPanel() {
  const panel = document.getElementById("quoteJsonPanel");
  const toggleBtn = document.getElementById("quoteJsonToggleBtn");
  const syncBtn = document.getElementById("quoteJsonSyncBtn");
  const saveBtn = document.getElementById("quoteJsonSaveBtn");
  if (!panel) return;
  const willShow = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !willShow);
  syncBtn?.classList.toggle("hidden", !willShow);
  saveBtn?.classList.toggle("hidden", !willShow);
  if (toggleBtn) toggleBtn.textContent = willShow ? "收起高级 JSON" : "展开高级 JSON";
  if (willShow) syncQuoteJsonFromForms(false);
}

async function saveQuotePolicies() {
  try {
    const payload = collectQuotePolicyForm();
    const data = await fetchJson("/api/admin/quote-policies", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    quotePolicyState.policy = data.item || payload;
    renderQuotePolicyForm(quotePolicyState.policy);
    syncQuoteJsonFromForms(false);
    showActionNotice("quotePolicyNotice", "报价策略已保存。", "success", { sticky: true });
  } catch (e) {
    showActionNotice("quotePolicyNotice", `保存失败：${e.message}`, "error", { sticky: true });
  }
}

async function savePricingCatalog() {
  try {
    const payload = collectPricingCatalogForm(true);
    const data = await fetchJson("/api/admin/pricing-catalog", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    quotePolicyState.catalog = normalizePricingCatalog(data.item || payload);
    renderPricingCatalog(quotePolicyState.catalog);
    syncQuoteJsonFromForms(false);
    showActionNotice(
      "pricingCatalogNotice",
      `价目表已保存：产品 ${quotePolicyState.catalog.products.length} 条，配件 ${quotePolicyState.catalog.accessories.length} 条。`,
      "success",
      { sticky: true }
    );
  } catch (e) {
    showActionNotice("pricingCatalogNotice", `保存失败：${e.message}`, "error", { sticky: true });
  }
}

async function saveQuoteJson() {
  const policyEl = document.getElementById("quotePolicyJson");
  const catalogEl = document.getElementById("pricingCatalogJson");
  let policy;
  let catalog;
  try {
    policy = JSON.parse(policyEl?.value || "{}");
    catalog = normalizePricingCatalog(JSON.parse(catalogEl?.value || "{}"));
  } catch (e) {
    showActionNotice("quoteJsonNotice", `JSON 解析失败：${e.message}`, "error", { sticky: true });
    return;
  }

  try {
    const policyData = await fetchJson("/api/admin/quote-policies", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(policy)
    });
    const catalogData = await fetchJson("/api/admin/pricing-catalog", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(catalog)
    });
    quotePolicyState.policy = policyData.item || policy;
    quotePolicyState.catalog = normalizePricingCatalog(catalogData.item || catalog);
    renderQuotePolicyForm(quotePolicyState.policy);
    renderPricingCatalog(quotePolicyState.catalog);
    syncQuoteJsonFromForms(false);
    showActionNotice("quoteJsonNotice", "JSON 已保存，表单已刷新。", "success", { sticky: true });
  } catch (e) {
    showActionNotice("quoteJsonNotice", `保存 JSON 失败：${e.message}`, "error", { sticky: true });
  }
}

async function rebuildPricingCatalogPreview() {
  quotePolicyState.catalog = collectPricingCatalogForm();
  const ok = window.confirm("将从知识库重新生成价目草稿，只替换当前页面草稿，不会自动覆盖已保存价目。继续吗？");
  if (!ok) return;
  showActionNotice("pricingCatalogNotice", "正在从知识库生成价目草稿...", "loading", { sticky: true });
  try {
    const data = await fetchJson("/api/admin/pricing-catalog/rebuild-preview", { method: "POST" });
    quotePolicyState.catalog = normalizePricingCatalog(data.item || data);
    renderPricingCatalog(quotePolicyState.catalog);
    syncQuoteJsonFromForms(false);
    showActionNotice(
      "pricingCatalogNotice",
      `已生成草稿：产品 ${quotePolicyState.catalog.products.length} 条，配件 ${quotePolicyState.catalog.accessories.length} 条。检查后点击“保存价目”才会写入。`,
      "success",
      { sticky: true }
    );
  } catch (e) {
    showActionNotice("pricingCatalogNotice", `生成草稿失败：${e.message}`, "error", { sticky: true });
  }
}

async function loadQuoteArchives(q = "") {
  const countEl = document.getElementById("quoteArchivesCount");
  const tbody = document.getElementById("quoteArchivesTableBody");
  if (!tbody) return;
  try {
    const data = await fetchJson(`/api/admin/quote-archives?q=${encodeURIComponent(q)}`);
    const items = Array.isArray(data.items) ? data.items : [];
    if (countEl) countEl.textContent = `共 ${data.total || 0} 条报价草案`;
    tbody.innerHTML = "";
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">暂无报价档案。带 user_id 的报价咨询会自动生成草案。</td></tr>`;
      return;
    }
    items.forEach((item) => {
      const tr = document.createElement("tr");
      const products = Array.isArray(item.recommended_products) ? item.recommended_products.join("、") : "-";
      const sources = Array.isArray(item.sources) ? item.sources.join("、") : "";
      const quoteItems = Array.isArray(item.quote_items) ? item.quote_items.map((x) => `${x.name || "-"} ${x.reference_price || ""}`).join("；") : "";
      tr.innerHTML = `
        <td>
          <strong>${escapeHtml(item.user_id || "-")}</strong>
          <div class="small">${escapeHtml(item.channel || "api")}</div>
          <div class="small">${escapeHtml(item.quote_id || "")}</div>
        </td>
        <td>
          <div>${escapeHtml(item.need_summary || "-")}</div>
          <div class="small">推荐：${escapeHtml(products)}</div>
          <div class="small">来源：${escapeHtml(sources)}</div>
        </td>
        <td>
          <div>${escapeHtml(item.reference_total || "-")}</div>
          <div class="small">${escapeHtml(quoteItems)}</div>
        </td>
        <td>${escapeHtml(item.status || "draft")}</td>
        <td>${escapeHtml(item.updated_at || "-")}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error(e);
    if (countEl) countEl.textContent = "报价档案加载失败";
  }
}

async function loadMemories(q = "") {
  const memoriesCount = document.getElementById("memoriesCount");
  const tbody = document.getElementById("memoriesTableBody");
  if (!tbody) return;

  try {
    const data = await fetchJson(`/api/admin/memories?q=${encodeURIComponent(q)}`);
    const items = Array.isArray(data.items) ? data.items : [];
    if (memoriesCount) memoriesCount.textContent = `共 ${data.total || 0} 个客户画像`;
    tbody.innerHTML = "";
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">暂无客户记忆。带 user_id 的聊天会自动生成关键画像。</td></tr>`;
      return;
    }
    items.forEach((item) => {
      const tr = document.createElement("tr");
      const channel = safeText(item.channel || "api");
      const userId = safeText(item.user_id || "");
      tr.innerHTML = `
        <td>
          <strong>${escapeHtml(item.customer_name || userId || "-")}</strong>
          <div class="small">${escapeHtml(channel)} / ${escapeHtml(userId)}</div>
          <div class="small">${escapeHtml(item.contact || "")}</div>
        </td>
        <td>
          <div>产品：${escapeHtml(joinMemoryList(item.products))}</div>
          <div>偏好：${escapeHtml(joinMemoryList(item.preferences))}</div>
          <div>场景：${escapeHtml(item.scenario || "-")} ｜ 预算：${escapeHtml(item.budget || "-")}</div>
          <div>关注：${escapeHtml(joinMemoryList(item.concerns))}</div>
          <div>常问：${escapeHtml(joinMemoryList((item.common_questions || []).slice(0, 2)))}</div>
          <div class="small">${escapeHtml(item.notes || "")}</div>
        </td>
        <td>${escapeHtml(joinMemoryList(item.risk_flags))}</td>
        <td>${escapeHtml(item.updated_at || "-")}</td>
        <td>
          <div class="table-actions">
            <button type="button" class="ghost-btn memory-edit-btn">编辑</button>
            <button type="button" class="danger-btn memory-delete-btn">删除</button>
          </div>
        </td>
      `;
      tr.querySelector(".memory-edit-btn")?.addEventListener("click", () => editMemory(item));
      tr.querySelector(".memory-delete-btn")?.addEventListener("click", () => deleteMemory(channel, userId));
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error(e);
    if (memoriesCount) memoriesCount.textContent = "客户记忆加载失败";
  }
}

async function editMemory(item) {
  const notes = prompt("编辑客户备注", item.notes || "");
  if (notes === null) return;
  const payload = { ...item, notes };
  try {
    await fetchJson(`/api/admin/memories/${encodeURIComponent(item.channel)}/${encodeURIComponent(item.user_id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    await loadMemories(document.getElementById("memorySearchInput")?.value || "");
    showResultModal("保存成功", "客户记忆已更新");
  } catch (e) {
    showResultModal("保存失败", `客户记忆保存失败：${e.message}`);
  }
}

async function deleteMemory(channel, userId) {
  if (!confirm(`确定删除 ${channel}/${userId} 的客户记忆吗？`)) return;
  try {
    await fetchJson(`/api/admin/memories/${encodeURIComponent(channel)}/${encodeURIComponent(userId)}`, {
      method: "DELETE"
    });
    await loadMemories(document.getElementById("memorySearchInput")?.value || "");
    showResultModal("删除成功", "客户记忆已删除");
  } catch (e) {
    showResultModal("删除失败", `客户记忆删除失败：${e.message}`);
  }
}

function renderFaqStats() {
  const totalEl = document.getElementById("faqTotalCount");
  const activeEl = document.getElementById("faqActiveCount");
  const inactiveEl = document.getElementById("faqInactiveCount");
  const countEl = document.getElementById("faqsCount");

  const total = faqState.items.length;
  const active = faqState.items.filter((x) => safeText(x.status) === "active").length;
  const inactive = total - active;

  if (totalEl) totalEl.textContent = safeText(total);
  if (activeEl) activeEl.textContent = safeText(active);
  if (inactiveEl) inactiveEl.textContent = safeText(inactive);

  if (countEl) {
    countEl.textContent = `共 ${faqState.items.length} 条，当前筛选后 ${faqState.filteredItems.length} 条`;
  }
}

function renderFaqCategoryOptions() {
  const faqCategoryInput = document.getElementById("faqCategoryInput");
  const faqCategoryFilter = document.getElementById("faqCategoryFilter");

  const names = sortByPriorityAndId(categoryState.items.map((x, idx) => ({
    id: `${idx}`,
    priority: 1,
    name: x.name
  }))).map((x) => x.name);

  if (faqCategoryInput) {
    const currentValue = faqCategoryInput.value;
    faqCategoryInput.innerHTML = `<option value="">请选择分类</option>`;
    names.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      faqCategoryInput.appendChild(option);
    });
    faqCategoryInput.value = names.includes(currentValue) ? currentValue : currentValue;
  }

  if (faqCategoryFilter) {
    const currentValue = faqCategoryFilter.value;
    faqCategoryFilter.innerHTML = `<option value="">全部类别</option>`;
    names.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      faqCategoryFilter.appendChild(option);
    });
    faqCategoryFilter.value = names.includes(currentValue) ? currentValue : "";
  }
}

function normalizeFaqEditorUi() {
  const faqIdInput = document.getElementById("faqIdInput");
  const faqStatusInput = document.getElementById("faqStatusInput");
  const faqStatusFilter = document.getElementById("faqStatusFilter");

  if (faqIdInput) {
    faqIdInput.readOnly = true;
    faqIdInput.setAttribute("readonly", "readonly");
    faqIdInput.placeholder = "系统自动生成";
  }

  if (faqStatusInput) {
    const currentValue = faqStatusInput.value === "inactive" ? "inactive" : "active";
    faqStatusInput.innerHTML = `
      <option value="active">已启用</option>
      <option value="inactive">未启动</option>
    `;
    faqStatusInput.value = currentValue;
  }

  if (faqStatusFilter) {
    const currentFilter = faqStatusFilter.value;
    faqStatusFilter.innerHTML = `
      <option value="">全部状态</option>
      <option value="active">已启用</option>
      <option value="inactive">未启动</option>
    `;
    faqStatusFilter.value = ["", "active", "inactive"].includes(currentFilter) ? currentFilter : "";
  }
}

function clearFaqQuestionRows() {
  const faqQuestionsList = document.getElementById("faqQuestionsList");
  if (faqQuestionsList) faqQuestionsList.innerHTML = "";
}

function updateFaqQuestionRowIndex() {
  const faqQuestionsList = document.getElementById("faqQuestionsList");
  if (!faqQuestionsList) return;

  Array.from(faqQuestionsList.querySelectorAll(".line-row")).forEach((row, index) => {
    const indexEl = row.querySelector(".line-index");
    if (indexEl) indexEl.textContent = String(index + 1).padStart(2, "0");
  });
}

function createFaqQuestionRow(value = "") {
  const row = document.createElement("div");
  row.className = "line-row";

  const indexEl = document.createElement("div");
  indexEl.className = "line-index";
  indexEl.textContent = "01";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "line-input faq-question-input";
  input.placeholder = "输入一个用户问法";
  input.value = value;

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "ghost-btn small-btn";
  removeBtn.textContent = "删除";
  removeBtn.addEventListener("click", () => {
    row.remove();
    const faqQuestionsList = document.getElementById("faqQuestionsList");
    if (faqQuestionsList && faqQuestionsList.children.length === 0) {
      addFaqQuestionRow("");
    }
    updateFaqQuestionRowIndex();
  });

  row.appendChild(indexEl);
  row.appendChild(input);
  row.appendChild(removeBtn);
  return row;
}

function addFaqQuestionRow(value = "") {
  const faqQuestionsList = document.getElementById("faqQuestionsList");
  if (!faqQuestionsList) return;
  faqQuestionsList.appendChild(createFaqQuestionRow(value));
  updateFaqQuestionRowIndex();
}

function getFaqQuestionValues() {
  return Array.from(document.querySelectorAll(".faq-question-input"))
    .map((el) => el.value.trim())
    .filter(Boolean);
}

function setFaqEditorMode(mode) {
  faqState.mode = mode;

  const faqEditorTitle = document.getElementById("faqEditorTitle");
  const faqEditorHint = document.getElementById("faqEditorHint");
  const faqEditorMode = document.getElementById("faqEditorMode");
  const faqIdRow = document.getElementById("faqIdRow");

  if (mode === "edit") {
    if (faqEditorTitle) faqEditorTitle.textContent = "编辑 FAQ";
    if (faqEditorHint) faqEditorHint.textContent = "修改后点击保存，系统会自动重新入库 FAQ 向量。";
    if (faqEditorMode) {
      faqEditorMode.textContent = "编辑";
      faqEditorMode.className = "status-badge green";
    }
    if (faqIdRow) faqIdRow.classList.remove("hidden");
  } else {
    if (faqEditorTitle) faqEditorTitle.textContent = "FAQ 编辑器";
    if (faqEditorHint) faqEditorHint.textContent = "点击左侧 FAQ 开始编辑，或新建一条 FAQ。";
    if (faqEditorMode) {
      faqEditorMode.textContent = "新建";
      faqEditorMode.className = "status-badge gray";
    }
    if (faqIdRow) faqIdRow.classList.add("hidden");
  }
}

function fillFaqForm(item) {
  const faqIdInput = document.getElementById("faqIdInput");
  const faqStatusInput = document.getElementById("faqStatusInput");
  const faqCategoryInput = document.getElementById("faqCategoryInput");
  const faqPriorityInput = document.getElementById("faqPriorityInput");
  const faqSourceInput = document.getElementById("faqSourceInput");
  const faqTagsInput = document.getElementById("faqTagsInput");
  const faqAnswerInput = document.getElementById("faqAnswerInput");

  if (faqIdInput) faqIdInput.value = safeText(item.id);
  if (faqStatusInput) faqStatusInput.value = safeText(item.status || "active");
  if (faqCategoryInput) faqCategoryInput.value = safeText(item.category);
  if (faqPriorityInput) faqPriorityInput.value = normalizePriority(item.priority || 1);
  if (faqSourceInput) faqSourceInput.value = safeText(item.source);
  if (faqTagsInput) faqTagsInput.value = Array.isArray(item.tags) ? item.tags.join(", ") : "";
  if (faqAnswerInput) faqAnswerInput.value = safeText(item.answer);

  clearFaqQuestionRows();
  const questions = Array.isArray(item.questions) ? item.questions : [];
  if (!questions.length) {
    addFaqQuestionRow("");
  } else {
    questions.forEach((q) => addFaqQuestionRow(q));
  }

  normalizeFaqEditorUi();
}

function resetFaqForm() {
  const faqIdInput = document.getElementById("faqIdInput");
  const faqStatusInput = document.getElementById("faqStatusInput");
  const faqCategoryInput = document.getElementById("faqCategoryInput");
  const faqPriorityInput = document.getElementById("faqPriorityInput");
  const faqSourceInput = document.getElementById("faqSourceInput");
  const faqTagsInput = document.getElementById("faqTagsInput");
  const faqAnswerInput = document.getElementById("faqAnswerInput");

  if (faqIdInput) faqIdInput.value = "";
  if (faqStatusInput) faqStatusInput.value = "active";
  if (faqCategoryInput) faqCategoryInput.value = "";
  if (faqPriorityInput) faqPriorityInput.value = 1;
  if (faqSourceInput) faqSourceInput.value = "";
  if (faqTagsInput) faqTagsInput.value = "";
  if (faqAnswerInput) faqAnswerInput.value = "";

  clearFaqQuestionRows();
  addFaqQuestionRow("");
  normalizeFaqEditorUi();
}

function buildFaqMeta(item) {
  const tags = Array.isArray(item.tags) ? item.tags : [];
  return `
    <div class="faq-card-meta">
      <span class="faq-chip">${escapeHtml(item.category || "未分类")}</span>
      <span class="faq-status-pill ${getFaqStatusClass(item.status)}">${getFaqStatusText(item.status)}</span>
      <span class="faq-chip faq-chip-light">优先级 ${escapeHtml(item.priority || 1)}</span>
      <span class="faq-chip faq-chip-light">问法 ${Array.isArray(item.questions) ? item.questions.length : 0}</span>
    </div>
    <div class="faq-card-sub">来源：${escapeHtml(item.source || "-")}</div>
    <div class="faq-card-sub">更新时间：${escapeHtml(item.updated_at || "-")}</div>
    <div class="faq-card-tags">
      ${tags.map((tag) => `<span class="tag tag-small">${escapeHtml(tag)}</span>`).join("")}
    </div>
  `;
}

function renderFaqList() {
  const faqListEl = document.getElementById("faqList");
  if (!faqListEl) return;

  faqListEl.innerHTML = "";

  if (!faqState.filteredItems.length) {
    faqListEl.innerHTML = `<div class="empty-block">没有符合条件的 FAQ</div>`;
    return;
  }

  faqState.filteredItems.forEach((item) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "faq-card" + (faqState.selectedId === item.id ? " active" : "");

    const questions = Array.isArray(item.questions) ? item.questions : [];
    const primaryQuestion = questions[0] || "(无问题)";
    const remainCount = Math.max(0, questions.length - 1);

    card.innerHTML = `
      <div class="faq-card-title">${escapeHtml(primaryQuestion)}</div>
      <div class="faq-card-desc">${remainCount > 0 ? `另有 ${remainCount} 个问法` : "仅 1 个问法"}</div>
      ${buildFaqMeta(item)}
    `;

    card.addEventListener("click", () => {
      selectFaq(item.id);
    });

    faqListEl.appendChild(card);
  });
}

function updateFaqSearchSummary() {
  const faqSearchCurrent = document.getElementById("faqSearchCurrent");
  if (!faqSearchCurrent) return;

  const parts = [];
  if (faqState.keyword) parts.push(`关键词：${faqState.keyword}`);
  if (faqState.category) parts.push(`类别：${faqState.category}`);
  if (faqState.status) parts.push(`状态：${getFaqStatusText(faqState.status)}`);

  faqSearchCurrent.textContent = parts.length
    ? `当前筛选：${parts.join(" ｜ ")}`
    : "当前筛选：全部 FAQ";
}

function applyFaqFilters() {
  faqState.filteredItems = sortByPriorityAndId(
    faqState.items.filter((item) => {
      if (faqState.category && safeText(item.category) !== faqState.category) return false;
      if (faqState.status && safeText(item.status) !== faqState.status) return false;

      if (!faqState.keyword) return true;

      const questionsText = Array.isArray(item.questions) ? item.questions.join(" ") : "";
      const tagsText = Array.isArray(item.tags) ? item.tags.join(" ") : "";
      const haystack = [
        safeText(item.id),
        safeText(item.category),
        safeText(item.source),
        safeText(item.answer),
        questionsText,
        tagsText,
        safeText(item.updated_at)
      ].join(" ").toLowerCase();

      return haystack.includes(faqState.keyword.toLowerCase());
    })
  );

  updateFaqSearchSummary();
  renderFaqStats();
  renderFaqList();

  if (faqState.selectedId && !faqState.filteredItems.some((item) => item.id === faqState.selectedId)) {
    faqState.selectedId = null;
    setFaqEditorMode("create");
    resetFaqForm();
  }
}

function startCreateFaq() {
  faqState.selectedId = null;
  setFaqEditorMode("create");
  resetFaqForm();
  renderFaqList();
}

function selectFaq(id) {
  const item = faqState.items.find((x) => x.id === id);
  if (!item) return;

  faqState.selectedId = id;
  setFaqEditorMode("edit");
  fillFaqForm(item);
  renderFaqList();
}

function collectFaqPayload() {
  const faqAnswerInput = document.getElementById("faqAnswerInput");
  const faqCategoryInput = document.getElementById("faqCategoryInput");
  const faqSourceInput = document.getElementById("faqSourceInput");
  const faqStatusInput = document.getElementById("faqStatusInput");
  const faqPriorityInput = document.getElementById("faqPriorityInput");
  const faqTagsInput = document.getElementById("faqTagsInput");

  const questions = getFaqQuestionValues();
  const answer = faqAnswerInput ? faqAnswerInput.value.trim() : "";
  const category = faqCategoryInput ? faqCategoryInput.value.trim() : "";
  const source = faqSourceInput ? faqSourceInput.value.trim() : "";
  const status = faqStatusInput ? faqStatusInput.value : "active";
  const priority = faqPriorityInput ? normalizePriority(faqPriorityInput.value) : 1;
  const tags = faqTagsInput
    ? faqTagsInput.value.split(",").map((x) => x.trim()).filter(Boolean)
    : [];

  if (!questions.length) {
    throw new Error("请至少填写一个问题问法");
  }

  if (!answer) {
    throw new Error("答案不能为空");
  }

  return {
    id: "",
    questions,
    answer,
    category,
    source,
    tags,
    status,
    priority
  };
}

async function loadFaqs() {
  try {
    const data = await fetchJson("/api/admin/faqs?q=");
    faqState.items = sortByPriorityAndId(Array.isArray(data.items) ? data.items : []);
    applyFaqFilters();

    if (faqState.selectedId) {
      const selected = faqState.items.find((x) => x.id === faqState.selectedId);
      if (selected) fillFaqForm(selected);
    }
  } catch (e) {
    console.error(e);
    showResultModal("加载失败", `加载 FAQ 失败：${e.message}`);
  }
}

async function saveFaq() {
  try {
    const payload = collectFaqPayload();
    let result;

    if (faqState.mode === "edit" && faqState.selectedId) {
      result = await fetchJson(`/api/admin/faqs/${encodeURIComponent(faqState.selectedId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      faqState.selectedId = result.item?.id || faqState.selectedId;
      showActionNotice("faqActionNotice", "FAQ 修改成功");
      showResultModal("FAQ 修改成功", formatReindexText(result.reindex));
    } else {
      result = await fetchJson("/api/admin/faqs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      faqState.selectedId = result.item?.id || null;
      setFaqEditorMode("edit");
      showActionNotice("faqActionNotice", "FAQ 新增成功");
      showResultModal("FAQ 新增成功", formatReindexText(result.reindex));
    }

    await loadSummary();
    await loadCategories();
    await loadFaqs();

    if (faqState.selectedId) {
      selectFaq(faqState.selectedId);
    }
  } catch (e) {
    showActionNotice("faqActionNotice", `保存失败：${e.message}`, "error");
    showResultModal("保存失败", `保存 FAQ 失败：${e.message}`);
  }
}

async function duplicateFaq() {
  try {
    const payload = collectFaqPayload();
    const result = await fetchJson("/api/admin/faqs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    faqState.selectedId = result.item?.id || null;
    await loadSummary();
    await loadCategories();
    await loadFaqs();

    if (faqState.selectedId) {
      selectFaq(faqState.selectedId);
    }

    showActionNotice("faqActionNotice", "FAQ 已另存为新条目");
    showResultModal("另存成功", formatReindexText(result.reindex));
  } catch (e) {
    showActionNotice("faqActionNotice", `另存失败：${e.message}`, "error");
    showResultModal("另存失败", `另存为新 FAQ 失败：${e.message}`);
  }
}

async function deleteCurrentFaq() {
  if (!faqState.selectedId) {
    showResultModal("提示", "请先选择一条 FAQ");
    return;
  }

  const ok = confirm(`确认删除 FAQ：${faqState.selectedId} 吗？`);
  if (!ok) return;

  try {
    const result = await fetchJson(`/api/admin/faqs/${encodeURIComponent(faqState.selectedId)}`, {
      method: "DELETE"
    });

    faqState.selectedId = null;
    startCreateFaq();

    await loadSummary();
    await loadCategories();
    await loadFaqs();

    showActionNotice("faqActionNotice", "FAQ 删除成功");
    showResultModal("删除成功", formatReindexText(result.reindex));
  } catch (e) {
    showActionNotice("faqActionNotice", `删除失败：${e.message}`, "error");
    showResultModal("删除失败", `删除 FAQ 失败：${e.message}`);
  }
}

async function reindexFaqs() {
  try {
    const result = await fetchJson("/api/admin/faqs/reindex", {
      method: "POST"
    });

    await loadSummary();
    await loadFaqs();

    showActionNotice("faqActionNotice", "FAQ 重新入库成功");
    showResultModal("FAQ 重新入库成功", formatReindexText(result.reindex));
  } catch (e) {
    showActionNotice("faqActionNotice", `重新入库失败：${e.message}`, "error");
    showResultModal("重新入库失败", `FAQ 重新入库失败：${e.message}`);
  }
}

function renderRuleCategoryOptions() {
  const ruleCategoryInput = document.getElementById("ruleCategoryInput");
  const names = sortByPriorityAndId(categoryState.items.map((x, idx) => ({
    id: `${idx}`,
    priority: 1,
    name: x.name
  }))).map((x) => x.name);

  if (ruleCategoryInput) {
    const currentValue = ruleCategoryInput.value;
    ruleCategoryInput.innerHTML = `<option value="">请选择分类</option>`;
    names.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      ruleCategoryInput.appendChild(option);
    });
    ruleCategoryInput.value = names.includes(currentValue) ? currentValue : currentValue;
  }
}

function clearRuleKeywordRows() {
  const ruleKeywordsList = document.getElementById("ruleKeywordsList");
  if (ruleKeywordsList) ruleKeywordsList.innerHTML = "";
}

function updateRuleKeywordRowIndex() {
  const ruleKeywordsList = document.getElementById("ruleKeywordsList");
  if (!ruleKeywordsList) return;

  Array.from(ruleKeywordsList.querySelectorAll(".line-row")).forEach((row, index) => {
    const indexEl = row.querySelector(".line-index");
    if (indexEl) indexEl.textContent = String(index + 1).padStart(2, "0");
  });
}

function createRuleKeywordRow(value = "") {
  const row = document.createElement("div");
  row.className = "line-row";

  const indexEl = document.createElement("div");
  indexEl.className = "line-index";
  indexEl.textContent = "01";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "line-input rule-keyword-input";
  input.placeholder = "输入一个关键词";
  input.value = value;

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "ghost-btn small-btn";
  removeBtn.textContent = "删除";
  removeBtn.addEventListener("click", () => {
    row.remove();
    const ruleKeywordsList = document.getElementById("ruleKeywordsList");
    if (ruleKeywordsList && ruleKeywordsList.children.length === 0) {
      addRuleKeywordRow("");
    }
    updateRuleKeywordRowIndex();
  });

  row.appendChild(indexEl);
  row.appendChild(input);
  row.appendChild(removeBtn);
  return row;
}

function addRuleKeywordRow(value = "") {
  const ruleKeywordsList = document.getElementById("ruleKeywordsList");
  if (!ruleKeywordsList) return;
  ruleKeywordsList.appendChild(createRuleKeywordRow(value));
  updateRuleKeywordRowIndex();
}

function getRuleKeywordValues() {
  return Array.from(document.querySelectorAll(".rule-keyword-input"))
    .map((el) => el.value.trim())
    .filter(Boolean);
}

function setRuleEditorMode(mode) {
  ruleState.mode = mode;

  const ruleEditorTitle = document.getElementById("ruleEditorTitle");
  const ruleEditorHint = document.getElementById("ruleEditorHint");
  const ruleEditorMode = document.getElementById("ruleEditorMode");
  const ruleIdRow = document.getElementById("ruleIdRow");

  if (mode === "edit") {
    if (ruleEditorTitle) ruleEditorTitle.textContent = "编辑规则";
    if (ruleEditorHint) ruleEditorHint.textContent = "修改后点击保存规则。";
    if (ruleEditorMode) {
      ruleEditorMode.textContent = "编辑";
      ruleEditorMode.className = "status-badge green";
    }
    if (ruleIdRow) ruleIdRow.classList.remove("hidden");
  } else {
    if (ruleEditorTitle) ruleEditorTitle.textContent = "规则编辑器";
    if (ruleEditorHint) ruleEditorHint.textContent = "点击左侧规则开始编辑，或新建一条规则。";
    if (ruleEditorMode) {
      ruleEditorMode.textContent = "新建";
      ruleEditorMode.className = "status-badge gray";
    }
    if (ruleIdRow) ruleIdRow.classList.add("hidden");
  }
}

function fillRuleForm(item) {
  const ruleIdInput = document.getElementById("ruleIdInput");
  const ruleNameInput = document.getElementById("ruleNameInput");
  const ruleCategoryInput = document.getElementById("ruleCategoryInput");
  const ruleStatusInput = document.getElementById("ruleStatusInput");
  const rulePriorityInput = document.getElementById("rulePriorityInput");
  const ruleActionInput = document.getElementById("ruleActionInput");
  const ruleNoteInput = document.getElementById("ruleNoteInput");

  if (ruleIdInput) ruleIdInput.value = safeText(item.id);
  if (ruleNameInput) ruleNameInput.value = safeText(item.rule_name);
  if (ruleCategoryInput) ruleCategoryInput.value = safeText(item.category);
  if (ruleStatusInput) ruleStatusInput.value = safeText(item.status || "active");
  if (rulePriorityInput) rulePriorityInput.value = normalizePriority(item.priority || 1);
  if (ruleActionInput) ruleActionInput.value = safeText(item.action || "faq_first");
  if (ruleNoteInput) ruleNoteInput.value = safeText(item.note);

  clearRuleKeywordRows();
  const keywords = normalizeRuleKeywords(item.keywords_text || item.keywords);
  if (!keywords.length) {
    addRuleKeywordRow("");
  } else {
    keywords.forEach((keyword) => addRuleKeywordRow(keyword));
  }
}

function resetRuleForm() {
  const ruleIdInput = document.getElementById("ruleIdInput");
  const ruleNameInput = document.getElementById("ruleNameInput");
  const ruleCategoryInput = document.getElementById("ruleCategoryInput");
  const ruleStatusInput = document.getElementById("ruleStatusInput");
  const rulePriorityInput = document.getElementById("rulePriorityInput");
  const ruleActionInput = document.getElementById("ruleActionInput");
  const ruleNoteInput = document.getElementById("ruleNoteInput");
  const ruleTestResult = document.getElementById("ruleTestResult");

  if (ruleIdInput) ruleIdInput.value = "";
  if (ruleNameInput) ruleNameInput.value = "";
  if (ruleCategoryInput) ruleCategoryInput.value = "";
  if (ruleStatusInput) ruleStatusInput.value = "active";
  if (rulePriorityInput) rulePriorityInput.value = 1;
  if (ruleActionInput) ruleActionInput.value = "faq_first";
  if (ruleNoteInput) ruleNoteInput.value = "";
  if (ruleTestResult) {
    ruleTestResult.className = "rule-test-result empty-result";
    ruleTestResult.textContent = "还没有测试结果";
  }

  clearRuleKeywordRows();
  addRuleKeywordRow("");
}

function buildRuleMeta(item) {
  const keywords = normalizeRuleKeywords(item.keywords_text || item.keywords);

  return `
    <div class="faq-card-meta">
      <span class="faq-chip">${escapeHtml(item.category || "未分类")}</span>
      <span class="faq-status-pill ${getRuleStatusClass(item.status)}">${getRuleStatusText(item.status)}</span>
      <span class="faq-chip faq-chip-light">优先级 ${escapeHtml(item.priority || 1)}</span>
      <span class="faq-chip faq-chip-light">${escapeHtml(getRuleActionText(item.action))}</span>
    </div>
    <div class="faq-card-sub">关键词：${escapeHtml(keywords.join(" | ") || "-")}</div>
    <div class="faq-card-sub">更新时间：${escapeHtml(item.updated_at || "-")}</div>
  `;
}

function renderRuleList() {
  const ruleListEl = document.getElementById("ruleList");
  const rulesCount = document.getElementById("rulesCount");

  if (!ruleListEl) return;
  ruleListEl.innerHTML = "";

  if (rulesCount) {
    rulesCount.textContent = `共 ${ruleState.items.length} 条，当前筛选后 ${ruleState.filteredItems.length} 条`;
  }

  if (!ruleState.filteredItems.length) {
    ruleListEl.innerHTML = `<div class="empty-block">没有符合条件的规则</div>`;
    return;
  }

  ruleState.filteredItems.forEach((item) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "faq-card" + (ruleState.selectedId === item.id ? " active" : "");

    card.innerHTML = `
      <div class="faq-card-title">${escapeHtml(item.rule_name || "(未命名规则)")}</div>
      <div class="faq-card-desc">${escapeHtml(getRuleActionText(item.action))}</div>
      ${buildRuleMeta(item)}
    `;

    card.addEventListener("click", () => {
      selectRule(item.id);
    });

    ruleListEl.appendChild(card);
  });
}

function applyRuleFilters() {
  ruleState.filteredItems = sortByPriorityAndId(
    ruleState.items.filter((item) => {
      if (!ruleState.keyword) return true;

      const keywordsText = normalizeRuleKeywords(item.keywords_text || item.keywords).join(" ");
      const haystack = [
        safeText(item.id),
        safeText(item.rule_name),
        safeText(item.category),
        safeText(item.note),
        safeText(item.action),
        safeText(item.status),
        keywordsText
      ].join(" ").toLowerCase();

      return haystack.includes(ruleState.keyword.toLowerCase());
    })
  );

  renderRuleList();

  if (ruleState.selectedId && !ruleState.filteredItems.some((item) => item.id === ruleState.selectedId)) {
    ruleState.selectedId = null;
    setRuleEditorMode("create");
    resetRuleForm();
  }
}

function startCreateRule() {
  ruleState.selectedId = null;
  setRuleEditorMode("create");
  resetRuleForm();
  renderRuleList();
}

function selectRule(id) {
  const item = ruleState.items.find((x) => x.id === id);
  if (!item) return;

  ruleState.selectedId = id;
  setRuleEditorMode("edit");
  fillRuleForm(item);
  renderRuleList();
}

function collectRulePayload() {
  const ruleNameInput = document.getElementById("ruleNameInput");
  const ruleCategoryInput = document.getElementById("ruleCategoryInput");
  const ruleStatusInput = document.getElementById("ruleStatusInput");
  const rulePriorityInput = document.getElementById("rulePriorityInput");
  const ruleActionInput = document.getElementById("ruleActionInput");
  const ruleNoteInput = document.getElementById("ruleNoteInput");

  const rule_name = ruleNameInput ? ruleNameInput.value.trim() : "";
  const keywords = getRuleKeywordValues();
  const category = ruleCategoryInput ? ruleCategoryInput.value.trim() : "";
  const status = ruleStatusInput ? ruleStatusInput.value : "active";
  const priority = rulePriorityInput ? normalizePriority(rulePriorityInput.value) : 1;
  const action = ruleActionInput ? ruleActionInput.value : "faq_first";
  const note = ruleNoteInput ? ruleNoteInput.value.trim() : "";

  if (!rule_name) {
    throw new Error("规则名不能为空");
  }

  if (!keywords.length) {
    throw new Error("请至少填写一个关键词");
  }

  return {
    id: "",
    rule_name,
    keywords,
    category,
    priority,
    status,
    action,
    note
  };
}

async function loadRules() {
  try {
    const data = await fetchJson("/api/admin/rules?q=");
    ruleState.items = sortByPriorityAndId(Array.isArray(data.items) ? data.items : []);
    applyRuleFilters();

    if (ruleState.selectedId) {
      const selected = ruleState.items.find((x) => x.id === ruleState.selectedId);
      if (selected) fillRuleForm(selected);
    }
  } catch (e) {
    console.error(e);
    showResultModal("加载失败", `加载规则失败：${e.message}`);
  }
}

async function saveRule() {
  try {
    const payload = collectRulePayload();
    let result;

    if (ruleState.mode === "edit" && ruleState.selectedId) {
      result = await fetchJson(`/api/admin/rules/${encodeURIComponent(ruleState.selectedId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      ruleState.selectedId = result.item?.id || ruleState.selectedId;
      showActionNotice("ruleActionNotice", "规则修改成功");
      showResultModal("规则修改成功", "规则已保存");
    } else {
      result = await fetchJson("/api/admin/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      ruleState.selectedId = result.item?.id || null;
      setRuleEditorMode("edit");
      showActionNotice("ruleActionNotice", "规则新增成功");
      showResultModal("规则新增成功", "规则已保存");
    }

    await loadSummary();
    await loadCategories();
    await loadRules();

    if (ruleState.selectedId) {
      selectRule(ruleState.selectedId);
    }
  } catch (e) {
    showActionNotice("ruleActionNotice", `保存失败：${e.message}`, "error");
    showResultModal("保存失败", `保存规则失败：${e.message}`);
  }
}

async function duplicateRule() {
  try {
    const payload = collectRulePayload();
    const result = await fetchJson("/api/admin/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    ruleState.selectedId = result.item?.id || null;
    await loadSummary();
    await loadCategories();
    await loadRules();

    if (ruleState.selectedId) {
      selectRule(ruleState.selectedId);
    }

    showActionNotice("ruleActionNotice", "规则已另存为新条目");
    showResultModal("另存成功", "规则已另存为新规则");
  } catch (e) {
    showActionNotice("ruleActionNotice", `另存失败：${e.message}`, "error");
    showResultModal("另存失败", `另存为新规则失败：${e.message}`);
  }
}

async function deleteCurrentRule() {
  if (!ruleState.selectedId) {
    showResultModal("提示", "请先选择一条规则");
    return;
  }

  const ok = confirm(`确认删除规则：${ruleState.selectedId} 吗？`);
  if (!ok) return;

  try {
    await fetchJson(`/api/admin/rules/${encodeURIComponent(ruleState.selectedId)}`, {
      method: "DELETE"
    });

    ruleState.selectedId = null;
    startCreateRule();

    await loadSummary();
    await loadCategories();
    await loadRules();

    showActionNotice("ruleActionNotice", "规则删除成功");
    showResultModal("删除成功", "规则已删除");
  } catch (e) {
    showActionNotice("ruleActionNotice", `删除失败：${e.message}`, "error");
    showResultModal("删除失败", `删除规则失败：${e.message}`);
  }
}

async function reloadRules() {
  try {
    await fetchJson("/api/admin/rules/reload", {
      method: "POST"
    });

    await loadSummary();
    await loadRules();

    showActionNotice("ruleActionNotice", "规则已重新加载");
    showResultModal("重新加载成功", "规则已重新加载");
  } catch (e) {
    showActionNotice("ruleActionNotice", `重新加载失败：${e.message}`, "error");
    showResultModal("重新加载失败", `规则重新加载失败：${e.message}`);
  }
}

async function testRuleMatch() {
  const ruleTestInput = document.getElementById("ruleTestInput");
  const ruleTestResult = document.getElementById("ruleTestResult");

  const text = ruleTestInput ? ruleTestInput.value.trim() : "";
  if (!text) {
    showResultModal("提示", "请输入要测试的客户问题");
    return;
  }

  try {
    const data = await fetchJson("/api/admin/rules/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });

    if (!ruleTestResult) return;

    if (data.matched && data.rule) {
      const rule = data.rule;
      const keywords = normalizeRuleKeywords(rule.keywords_text || rule.keywords);
      ruleTestResult.className = "rule-test-result";
      ruleTestResult.innerHTML = `
        <div><strong>命中结果：</strong>已命中规则</div>
        <div><strong>规则名：</strong>${escapeHtml(rule.rule_name || "-")}</div>
        <div><strong>分类：</strong>${escapeHtml(rule.category || "-")}</div>
        <div><strong>状态：</strong>${escapeHtml(getRuleStatusText(rule.status || "active"))}</div>
        <div><strong>动作：</strong>${escapeHtml(getRuleActionText(rule.action || "faq_first"))}</div>
        <div><strong>关键词：</strong>${escapeHtml(keywords.join(" | ") || "-")}</div>
      `;
    } else {
      ruleTestResult.className = "rule-test-result empty-result";
      ruleTestResult.textContent = "未命中任何规则";
    }
  } catch (e) {
    showResultModal("测试失败", `规则测试失败：${e.message}`);
  }
}

async function loadCategories() {
  try {
    const data = await fetchJson("/api/admin/categories");
    categoryState.items = Array.isArray(data.items) ? data.items : [];
    renderFaqCategoryOptions();
    renderRuleCategoryOptions();
    renderCategoryList();
  } catch (e) {
    console.error(e);
  }
}

function renderCategoryList() {
  const categoryList = document.getElementById("categoryList");
  if (!categoryList) return;

  categoryList.innerHTML = "";

  if (!categoryState.items.length) {
    categoryList.innerHTML = `<div class="empty-block">暂无分类</div>`;
    return;
  }

  categoryState.items.forEach((item) => {
    const row = document.createElement("div");
    const used = Number(item.faq_count || 0) > 0 || Number(item.rule_count || 0) > 0;
    row.className = "category-row " + (used ? "is-used" : "is-free");
    const deleteDisabled = used ? "disabled" : "";

    row.innerHTML = `
      <div class="category-row-main">
        <div class="category-row-title">${escapeHtml(item.name || "")}</div>
        <div class="category-row-meta">
          <span class="category-count-badge">FAQ ${escapeHtml(item.faq_count || 0)}</span>
          <span class="category-count-badge">规则 ${escapeHtml(item.rule_count || 0)}</span>
          <span class="category-state-badge ${used ? "category-state-used" : "category-state-free"}">${used ? "使用中" : "可删除"}</span>
        </div>
      </div>
      <button type="button" class="danger-btn category-delete-btn" data-name="${escapeHtml(item.name || "")}" ${deleteDisabled}>删除</button>
    `;

    const btn = row.querySelector(".category-delete-btn");
    if (btn && !used) {
      btn.addEventListener("click", async () => {
        await deleteCategory(item.name);
      });
    }

    categoryList.appendChild(row);
  });
}

function openCategoryModal(target) {
  categoryState.target = target;
  const modal = document.getElementById("categoryModal");
  if (modal) modal.classList.remove("hidden");
  const categoryNameInput = document.getElementById("categoryNameInput");
  if (categoryNameInput) {
    categoryNameInput.value = "";
    setTimeout(() => categoryNameInput.focus(), 0);
  }
}

function closeCategoryModal() {
  const modal = document.getElementById("categoryModal");
  if (modal) modal.classList.add("hidden");
}

async function addCategory() {
  const categoryNameInput = document.getElementById("categoryNameInput");
  const name = categoryNameInput ? categoryNameInput.value.trim() : "";

  if (!name) {
    showResultModal("提示", "请输入分类名称");
    return;
  }

  try {
    await fetchJson("/api/admin/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });

    await loadCategories();

    if (categoryState.target === "faq") {
      const faqCategoryInput = document.getElementById("faqCategoryInput");
      if (faqCategoryInput) faqCategoryInput.value = name;
    } else {
      const ruleCategoryInput = document.getElementById("ruleCategoryInput");
      if (ruleCategoryInput) ruleCategoryInput.value = name;
    }

    if (categoryNameInput) categoryNameInput.value = "";
    showResultModal("新增成功", "分类已新增");
  } catch (e) {
    showResultModal("新增失败", `新增分类失败：${e.message}`);
  }
}

async function deleteCategory(name) {
  const ok = confirm(`确认删除分类：${name} 吗？`);
  if (!ok) return;

  try {
    await fetchJson(`/api/admin/categories/${encodeURIComponent(name)}`, {
      method: "DELETE"
    });

    await loadCategories();
    showResultModal("删除成功", "分类已删除");
  } catch (e) {
    showResultModal("删除失败", `删除分类失败：${e.message}`);
  }
}

function bindBaseEvents() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
    });
  });

  if (refreshAllBtn) {
    refreshAllBtn.addEventListener("click", async () => {
      await initAdmin();
    });
  }

  const serviceStartBtn = document.getElementById("serviceStartBtn");
  const serviceRestartBtn = document.getElementById("serviceRestartBtn");
  const serviceStopBtn = document.getElementById("serviceStopBtn");
  const qdrantStartBtn = document.getElementById("qdrantStartBtn");
  if (serviceStartBtn) serviceStartBtn.addEventListener("click", () => runServiceAction("start-all"));
  if (serviceRestartBtn) serviceRestartBtn.addEventListener("click", () => runServiceAction("restart-all"));
  if (serviceStopBtn) serviceStopBtn.addEventListener("click", () => runServiceAction("stop-all"));
  if (qdrantStartBtn) qdrantStartBtn.addEventListener("click", () => runServiceAction("qdrant/start"));

  const memorySearchInput = document.getElementById("memorySearchInput");
  const memorySearchBtn = document.getElementById("memorySearchBtn");
  if (memorySearchBtn) memorySearchBtn.addEventListener("click", () => loadMemories(memorySearchInput?.value || ""));
  if (memorySearchInput) {
    memorySearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") loadMemories(memorySearchInput.value || "");
    });
  }

  const quotePolicySaveBtn = document.getElementById("quotePolicySaveBtn");
  const pricingCatalogSaveBtn = document.getElementById("pricingCatalogSaveBtn");
  const pricingAddProductBtn = document.getElementById("pricingAddProductBtn");
  const pricingAddAccessoryBtn = document.getElementById("pricingAddAccessoryBtn");
  const pricingRebuildPreviewBtn = document.getElementById("pricingRebuildPreviewBtn");
  const quoteJsonToggleBtn = document.getElementById("quoteJsonToggleBtn");
  const quoteJsonSyncBtn = document.getElementById("quoteJsonSyncBtn");
  const quoteJsonSaveBtn = document.getElementById("quoteJsonSaveBtn");
  const quoteArchiveSearchInput = document.getElementById("quoteArchiveSearchInput");
  const quoteArchiveSearchBtn = document.getElementById("quoteArchiveSearchBtn");
  if (quotePolicySaveBtn) quotePolicySaveBtn.addEventListener("click", saveQuotePolicies);
  if (pricingCatalogSaveBtn) pricingCatalogSaveBtn.addEventListener("click", savePricingCatalog);
  if (pricingAddProductBtn) pricingAddProductBtn.addEventListener("click", addPricingProduct);
  if (pricingAddAccessoryBtn) pricingAddAccessoryBtn.addEventListener("click", addPricingAccessory);
  if (pricingRebuildPreviewBtn) pricingRebuildPreviewBtn.addEventListener("click", rebuildPricingCatalogPreview);
  if (quoteJsonToggleBtn) quoteJsonToggleBtn.addEventListener("click", toggleQuoteJsonPanel);
  if (quoteJsonSyncBtn) quoteJsonSyncBtn.addEventListener("click", () => syncQuoteJsonFromForms(true));
  if (quoteJsonSaveBtn) quoteJsonSaveBtn.addEventListener("click", saveQuoteJson);
  if (quoteArchiveSearchBtn) quoteArchiveSearchBtn.addEventListener("click", () => loadQuoteArchives(quoteArchiveSearchInput?.value || ""));
  if (quoteArchiveSearchInput) {
    quoteArchiveSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") loadQuoteArchives(quoteArchiveSearchInput.value || "");
    });
  }

  const resultModalClose = document.getElementById("resultModalClose");
  const resultModalConfirm = document.getElementById("resultModalConfirm");
  const resultModal = document.getElementById("resultModal");

  if (resultModalClose) resultModalClose.addEventListener("click", hideResultModal);
  if (resultModalConfirm) resultModalConfirm.addEventListener("click", hideResultModal);
  if (resultModal) {
    resultModal.addEventListener("click", (e) => {
      if (e.target === resultModal) hideResultModal();
    });
  }

  const docSearchBtn = document.getElementById("docSearchBtn");
  const docSearchInput = document.getElementById("docSearchInput");
  const docSelectAll = document.getElementById("docSelectAll");
  const docBatchDeleteBtn = document.getElementById("docBatchDeleteBtn");
  const docViewModeBtn = document.getElementById("docViewModeBtn");
  const chunkViewModeBtn = document.getElementById("chunkViewModeBtn");
  if (docSearchBtn) {
    docSearchBtn.addEventListener("click", async () => {
      await loadDocs(docSearchInput ? docSearchInput.value.trim() : "");
    });
  }
  if (docViewModeBtn) {
    docViewModeBtn.addEventListener("click", () => setDocsViewMode("docs"));
  }
  if (chunkViewModeBtn) {
    chunkViewModeBtn.addEventListener("click", () => setDocsViewMode("chunks"));
  }
  if (docSelectAll) {
    docSelectAll.addEventListener("change", () => {
      setAllVisibleDocsSelected(docSelectAll.checked);
    });
  }
  if (docBatchDeleteBtn) {
    docBatchDeleteBtn.addEventListener("click", batchDeleteDocs);
  }
  if (docSearchInput) {
    docSearchInput.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        await loadDocs(docSearchInput.value.trim());
      }
    });
  }

  const docUploadForm = document.getElementById("docUploadForm");
  const docUploadFile = document.getElementById("docUploadFile");
  if (docUploadFile) {
    docUploadFile.addEventListener("change", updateDocUploadSelection);
  }
  if (docUploadForm) {
    docUploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await uploadDocFile();
    });
  }

  const reloadLogBtn = document.getElementById("reloadLogBtn");
  if (reloadLogBtn) {
    reloadLogBtn.addEventListener("click", async () => {
      await loadLogs();
    });
  }
}

function bindFaqEvents() {
  const faqToggleSearchBtn = document.getElementById("faqToggleSearchBtn");
  const faqSearchResetBtn = document.getElementById("faqSearchResetBtn");
  const faqSearchPopover = document.getElementById("faqSearchPopover");
  const faqSearchPopoverClose = document.getElementById("faqSearchPopoverClose");
  const faqKeywordInput = document.getElementById("faqKeywordInput");
  const faqSearchBtn = document.getElementById("faqSearchBtn");
  const faqCategoryFilter = document.getElementById("faqCategoryFilter");
  const faqStatusFilter = document.getElementById("faqStatusFilter");

  const faqAddBtn = document.getElementById("faqAddBtn");
  const faqReindexBtn = document.getElementById("faqReindexBtn");
  const addQuestionBtn = document.getElementById("addQuestionBtn");
  const faqNewBtn = document.getElementById("faqNewBtn");
  const faqDuplicateBtn = document.getElementById("faqDuplicateBtn");
  const faqDeleteBtn = document.getElementById("faqDeleteBtn");
  const faqForm = document.getElementById("faqForm");
  const faqManageCategoryBtn = document.getElementById("faqManageCategoryBtn");

  if (faqToggleSearchBtn && faqSearchPopover) {
    faqToggleSearchBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const hidden = faqSearchPopover.classList.contains("hidden");
      closeAllPopovers();
      if (hidden) {
        faqSearchPopover.classList.remove("hidden");
        if (faqKeywordInput) setTimeout(() => faqKeywordInput.focus(), 0);
      }
    });
  }

  if (faqSearchPopoverClose && faqSearchPopover) {
    faqSearchPopoverClose.addEventListener("click", () => {
      faqSearchPopover.classList.add("hidden");
    });
  }

  if (faqSearchBtn) {
    faqSearchBtn.addEventListener("click", () => {
      faqState.keyword = faqKeywordInput ? faqKeywordInput.value.trim() : "";
      faqState.category = faqCategoryFilter ? faqCategoryFilter.value : "";
      faqState.status = faqStatusFilter ? faqStatusFilter.value : "";
      applyFaqFilters();
      if (faqSearchPopover) faqSearchPopover.classList.add("hidden");
    });
  }

  if (faqKeywordInput) {
    faqKeywordInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        faqState.keyword = faqKeywordInput.value.trim();
        faqState.category = faqCategoryFilter ? faqCategoryFilter.value : "";
        faqState.status = faqStatusFilter ? faqStatusFilter.value : "";
        applyFaqFilters();
        if (faqSearchPopover) faqSearchPopover.classList.add("hidden");
      }
    });
  }

  if (faqCategoryFilter) {
    faqCategoryFilter.addEventListener("change", () => {
      faqState.category = faqCategoryFilter.value;
      applyFaqFilters();
    });
  }

  if (faqStatusFilter) {
    faqStatusFilter.addEventListener("change", () => {
      faqState.status = faqStatusFilter.value;
      applyFaqFilters();
    });
  }

  if (faqSearchResetBtn) {
    faqSearchResetBtn.addEventListener("click", () => {
      faqState.keyword = "";
      faqState.category = "";
      faqState.status = "";
      if (faqKeywordInput) faqKeywordInput.value = "";
      if (faqCategoryFilter) faqCategoryFilter.value = "";
      if (faqStatusFilter) faqStatusFilter.value = "";
      applyFaqFilters();
    });
  }

  if (faqAddBtn) faqAddBtn.addEventListener("click", startCreateFaq);
  if (faqReindexBtn) faqReindexBtn.addEventListener("click", reindexFaqs);
  if (addQuestionBtn) addQuestionBtn.addEventListener("click", () => addFaqQuestionRow(""));
  if (faqNewBtn) faqNewBtn.addEventListener("click", startCreateFaq);
  if (faqDuplicateBtn) faqDuplicateBtn.addEventListener("click", duplicateFaq);
  if (faqDeleteBtn) faqDeleteBtn.addEventListener("click", deleteCurrentFaq);
  if (faqManageCategoryBtn) {
    faqManageCategoryBtn.addEventListener("click", () => {
      openCategoryModal("faq");
    });
  }

  if (faqForm) {
    faqForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await saveFaq();
    });
  }
}

function bindRuleEvents() {
  const ruleToggleSearchBtn = document.getElementById("ruleToggleSearchBtn");
  const ruleSearchResetBtn = document.getElementById("ruleSearchResetBtn");
  const ruleSearchPopover = document.getElementById("ruleSearchPopover");
  const ruleSearchPopoverClose = document.getElementById("ruleSearchPopoverClose");
  const ruleKeywordInput = document.getElementById("ruleKeywordInput");
  const ruleSearchBtn = document.getElementById("ruleSearchBtn");

  const ruleAddBtn = document.getElementById("ruleAddBtn");
  const ruleReloadBtn = document.getElementById("ruleReloadBtn");
  const addRuleKeywordBtn = document.getElementById("addRuleKeywordBtn");
  const ruleNewBtn = document.getElementById("ruleNewBtn");
  const ruleDuplicateBtn = document.getElementById("ruleDuplicateBtn");
  const ruleDeleteBtn = document.getElementById("ruleDeleteBtn");
  const ruleForm = document.getElementById("ruleForm");
  const ruleTestBtn = document.getElementById("ruleTestBtn");
  const ruleManageCategoryBtn = document.getElementById("ruleManageCategoryBtn");

  if (ruleToggleSearchBtn && ruleSearchPopover) {
    ruleToggleSearchBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const hidden = ruleSearchPopover.classList.contains("hidden");
      closeAllPopovers();
      if (hidden) {
        ruleSearchPopover.classList.remove("hidden");
        if (ruleKeywordInput) setTimeout(() => ruleKeywordInput.focus(), 0);
      }
    });
  }

  if (ruleSearchPopoverClose && ruleSearchPopover) {
    ruleSearchPopoverClose.addEventListener("click", () => {
      ruleSearchPopover.classList.add("hidden");
    });
  }

  if (ruleSearchBtn) {
    ruleSearchBtn.addEventListener("click", () => {
      ruleState.keyword = ruleKeywordInput ? ruleKeywordInput.value.trim() : "";
      applyRuleFilters();
      if (ruleSearchPopover) ruleSearchPopover.classList.add("hidden");
    });
  }

  if (ruleKeywordInput) {
    ruleKeywordInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        ruleState.keyword = ruleKeywordInput.value.trim();
        applyRuleFilters();
        if (ruleSearchPopover) ruleSearchPopover.classList.add("hidden");
      }
    });
  }

  if (ruleSearchResetBtn) {
    ruleSearchResetBtn.addEventListener("click", () => {
      ruleState.keyword = "";
      if (ruleKeywordInput) ruleKeywordInput.value = "";
      applyRuleFilters();
    });
  }

  if (ruleAddBtn) ruleAddBtn.addEventListener("click", startCreateRule);
  if (ruleReloadBtn) ruleReloadBtn.addEventListener("click", reloadRules);
  if (addRuleKeywordBtn) addRuleKeywordBtn.addEventListener("click", () => addRuleKeywordRow(""));
  if (ruleNewBtn) ruleNewBtn.addEventListener("click", startCreateRule);
  if (ruleDuplicateBtn) ruleDuplicateBtn.addEventListener("click", duplicateRule);
  if (ruleDeleteBtn) ruleDeleteBtn.addEventListener("click", deleteCurrentRule);
  if (ruleTestBtn) ruleTestBtn.addEventListener("click", testRuleMatch);
  if (ruleManageCategoryBtn) {
    ruleManageCategoryBtn.addEventListener("click", () => {
      openCategoryModal("rule");
    });
  }

  if (ruleForm) {
    ruleForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await saveRule();
    });
  }
}

function bindCategoryEvents() {
  const categoryModal = document.getElementById("categoryModal");
  const categoryModalClose = document.getElementById("categoryModalClose");
  const categoryModalDone = document.getElementById("categoryModalDone");
  const categoryAddBtn = document.getElementById("categoryAddBtn");
  const categoryNameInput = document.getElementById("categoryNameInput");

  if (categoryModalClose) categoryModalClose.addEventListener("click", closeCategoryModal);
  if (categoryModalDone) categoryModalDone.addEventListener("click", closeCategoryModal);
  if (categoryAddBtn) categoryAddBtn.addEventListener("click", addCategory);

  if (categoryNameInput) {
    categoryNameInput.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        await addCategory();
      }
    });
  }

  if (categoryModal) {
    categoryModal.addEventListener("click", (e) => {
      if (e.target === categoryModal) closeCategoryModal();
    });
  }
}

function bindGlobalClickClose() {
  document.addEventListener("click", (e) => {
    const faqSearchPopover = document.getElementById("faqSearchPopover");
    const ruleSearchPopover = document.getElementById("ruleSearchPopover");
    const faqToggleSearchBtn = document.getElementById("faqToggleSearchBtn");
    const ruleToggleSearchBtn = document.getElementById("ruleToggleSearchBtn");

    if (
      faqSearchPopover &&
      !faqSearchPopover.classList.contains("hidden") &&
      !faqSearchPopover.contains(e.target) &&
      faqToggleSearchBtn &&
      !faqToggleSearchBtn.contains(e.target)
    ) {
      faqSearchPopover.classList.add("hidden");
    }

    if (
      ruleSearchPopover &&
      !ruleSearchPopover.classList.contains("hidden") &&
      !ruleSearchPopover.contains(e.target) &&
      ruleToggleSearchBtn &&
      !ruleToggleSearchBtn.contains(e.target)
    ) {
      ruleSearchPopover.classList.add("hidden");
    }
  });
}

async function initAdmin() {
  normalizeFaqEditorUi();
  setFaqEditorMode("create");
  setRuleEditorMode("create");
  resetFaqForm();
  resetRuleForm();

  await loadStatus();
  await loadServiceControlStatus();
  await loadSummary();
  await loadCategories();
  await loadDocs();
  await loadFaqs();
  await loadRules();
  await loadQuotePolicies();
  await loadQuoteArchives();
  await loadMemories();
  await loadLogs();

  renderFaqStats();
  switchTab("dashboard");
}

bindBaseEvents();
bindFaqEvents();
bindRuleEvents();
bindCategoryEvents();
bindGlobalClickClose();
initAdmin();
