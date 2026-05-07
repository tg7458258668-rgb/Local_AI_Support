const chatBox = document.getElementById("chat-box");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");

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

function formatRichText(text) {
  if (text === null || text === undefined) return "";

  let safe = escapeHtml(String(text));

  // 连续 3 个以上换行，压缩成 2 个
  safe = safe.replace(/\n{3,}/g, "\n\n");

  // markdown 粗体 **xxx**
  safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

  // 双换行转段落
  const paragraphs = safe
    .split(/\n\s*\n/)
    .map(p => p.trim())
    .filter(Boolean)
    .map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`);

  return paragraphs.join("");
}

function appendUserMessage(text) {
  const wrap = document.createElement("div");
  wrap.className = "message user";
  wrap.innerHTML = `
    <div class="bubble">
      <div class="answer-text">${escapeHtml(text)}</div>
    </div>
  `;
  chatBox.appendChild(wrap);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function appendLoadingMessage() {
  const wrap = document.createElement("div");
  wrap.className = "message ai";
  wrap.id = "loading-message";
  wrap.innerHTML = `
    <div class="bubble">
      <div class="answer-text loading">正在思考，请稍候...</div>
    </div>
  `;
  chatBox.appendChild(wrap);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function removeLoadingMessage() {
  const el = document.getElementById("loading-message");
  if (el) el.remove();
}

function formatMatchedRule(matchedRule) {
  if (!matchedRule) return "无";
  if (typeof matchedRule === "string") return matchedRule;
  if (typeof matchedRule === "object") {
    return matchedRule.rule_name || matchedRule.id || "无";
  }
  return "无";
}

function formatHint(data) {
  if (data.hint) return data.hint;
  if (data.tip) return data.tip;
  if (data.note) return data.note;
  if (data.human_check) return data.human_check;
  if (
    data.need_human === true ||
    data.need_handoff === true ||
    data.should_human_confirm === true
  ) {
    return "本回答建议人工进一步确认";
  }
  return "当前未触发人工接管提示";
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

function appendAiMessage(data) {
  const answer = data.answer || data.response || "暂无回答";
  const route = data.route || "-";
  const matchedRule = formatMatchedRule(data.matched_rule);
  const faqScore = formatScore(data.faq_score);
  const docScore = formatScore(data.doc_score);
  const hint = formatHint(data);
  const sources = Array.isArray(data.sources) ? data.sources : [];

  let sourcesHtml = "";
  if (sources.length > 0) {
    sourcesHtml = `
      <div class="source-title">来源：</div>
      <ul class="source-list">
        ${sources.map(item => `<li>${escapeHtml(buildSourceText(item))}</li>`).join("")}
      </ul>
    `;
  }

  const wrap = document.createElement("div");
  wrap.className = "message ai";
  wrap.innerHTML = `
    <div class="bubble">
      <div class="answer-text">${formatRichText(answer)}</div>
      <div class="meta">
        <div class="meta-line"><strong>路由：</strong>${escapeHtml(route)}</div>
        <div class="meta-line"><strong>规则命中：</strong>${escapeHtml(matchedRule)}</div>
        <div class="meta-line"><strong>FAQ分数：</strong>${escapeHtml(faqScore)}</div>
        <div class="meta-line"><strong>DOC分数：</strong>${escapeHtml(docScore)}</div>
        <div class="meta-line tip-line"><strong>提示：</strong>${escapeHtml(hint)}</div>
        ${sourcesHtml}
      </div>
    </div>
  `;
  chatBox.appendChild(wrap);
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;

  appendUserMessage(question);
  questionInput.value = "";
  appendLoadingMessage();

  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ question })
    });

    const data = await resp.json();
    removeLoadingMessage();
    appendAiMessage(data);
  } catch (err) {
    removeLoadingMessage();
    appendAiMessage({
      answer: `请求失败：${err}`,
      route: "-",
      matched_rule: "无",
      faq_score: "-",
      doc_score: "-",
      hint: "请检查后端服务是否正常运行",
      sources: []
    });
  }
}

sendBtn.addEventListener("click", sendQuestion);

clearBtn.addEventListener("click", () => {
  chatBox.innerHTML = `
    <div class="message ai">
      <div class="bubble">
        <div class="answer-text">
          你好，我是本地 AI 客服助手。你可以直接问我产品、保修、售后等问题。
        </div>
      </div>
    </div>
  `;
  questionInput.value = "";
});

questionInput.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    sendQuestion();
  }
});