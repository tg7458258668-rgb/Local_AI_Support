// 聊天逻辑
async function askQuestion() {
  const questionInput = document.getElementById("user-question");
  const question = questionInput.value.trim();
  if(!question) return;
  appendMessage("user", question);
  questionInput.value = "";
  try {
    const res = await fetch("/ask", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({question})
    });
    const data = await res.json();
    appendMessage("ai", data.answer || "未找到答案");
    appendMeta(data);
  } catch(err) { appendMessage("ai", "请求失败：" + err); }
}

function appendMessage(role, text) {
  const chatBox = document.getElementById("chat-box");
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${role}`;
  msgDiv.innerHTML = text.replace(/\n/g,"<br>");
  chatBox.appendChild(msgDiv);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function appendMeta(data){
  const chatBox = document.getElementById("chat-box");
  const metaDiv = document.createElement("div");
  metaDiv.className="meta-line";
  metaDiv.innerHTML = `
    路由：${data.route||"-"} <br>
    规则命中：${data.matched_rule||"无"} <br>
    提示：${data.human_check||"-"} <br>
    来源：${data.sources ? data.sources.map(s=>s.source+"["+s.section+"]").join(" | ") : "-"}
  `;
  chatBox.appendChild(metaDiv);
}

// 系统控制逻辑（模拟 API）
async function startSystem(){await fetch("/system/start",{method:"POST"}); updateSystemStatus();}
async function stopSystem(){await fetch("/system/stop",{method:"POST"}); updateSystemStatus();}
async function restartSystem(){await fetch("/system/restart",{method:"POST"}); updateSystemStatus();}
async function forceRestartSystem(){await fetch("/system/force_restart",{method:"POST"}); updateSystemStatus();}
async function saveLogs(){const res=await fetch("/system/save_logs",{method:"POST"});const data=await res.json(); alert("日志已保存:\n"+data.saved_logs.join("\n"));}

// 模拟状态
function updateSystemStatus(){
  document.getElementById("ollama-status").innerText="🟢 在线";
  document.getElementById("qdrant-status").innerText="🟢 在线";
  document.getElementById("backend-status").innerText="🟢 在线";
}

// 日志模拟
setInterval(()=>{
  const logBox = document.getElementById("log-box");
  logBox.innerText = "系统日志示例...\n" + new Date().toLocaleTimeString();
},2000);