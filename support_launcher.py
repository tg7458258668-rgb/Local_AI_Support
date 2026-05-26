from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from support_app.services.system_control import LocalSupportSystem

BASE_DIR = Path(__file__).resolve().parent
system = LocalSupportSystem(BASE_DIR)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class LauncherHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self._send_json({"ok": True})

    def do_GET(self):
        if self.path == "/api/system/status":
            self._send_json(system.status())
            return
        self._send_html(self._page())

    def do_POST(self):
        if self.path in ("/api/system/start", "/api/system/start-all"):
            self._send_json(system.start_all())
            return
        if self.path in ("/api/system/stop", "/api/system/stop-all"):
            self._send_json(system.stop_all())
            return
        if self.path in ("/api/system/restart", "/api/system/restart-all"):
            self._send_json(system.restart_all())
            return
        if self.path == "/api/system/app/start":
            self._send_json(system.app.start())
            return
        if self.path == "/api/system/app/stop":
            self._send_json(system.app.stop())
            return
        if self.path == "/api/system/app/restart":
            self._send_json(system.app.restart())
            return
        if self.path == "/api/system/qdrant/start":
            self._send_json(system.qdrant.start())
            return
        if self.path == "/api/system/qdrant/stop":
            self._send_json(system.qdrant.stop())
            return
        if self.path == "/api/system/qdrant/restart":
            self._send_json(system.qdrant.restart())
            return
        self.send_error(404)

    def log_message(self, format, *args):
        return

    def _send_json(self, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _page() -> str:
        return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>本地 AI 客服启动器</title>
  <style>
    * { box-sizing: border-box; }
    :root {
      --panel: #121212;
      --panel-soft: #1a1a1a;
      --panel-strong: #0f0f0f;
      --line: #262626;
      --line-strong: #333333;
      --text: #f3f4f6;
      --muted: #8b8b8b;
      --dim: #5b5b5b;
      --green: #10b981;
      --red: #f87171;
      --blue: #60a5fa;
      --radius: 12px;
    }
    html, body { min-width: 0; min-height: 100%; margin: 0; padding: 0; }
    body {
      min-height: 100dvh;
      display: grid;
      place-items: center;
      overflow: auto;
      background:
        radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.16), transparent 34%),
        #050505;
      color: var(--text);
      font-family: "Avenir Next", "PingFang SC", "Microsoft YaHei", ui-sans-serif, sans-serif;
      letter-spacing: 0;
    }
    button, a {
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 9px;
      cursor: pointer;
      color: inherit;
      font: inherit;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0;
      text-decoration: none;
      touch-action: manipulation;
      position: relative;
      overflow: hidden;
      transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, color 0.18s ease;
    }
    button:focus-visible, a:focus-visible { outline: 3px solid rgba(96, 165, 250, 0.36); outline-offset: 2px; }
    button:hover, a:hover { transform: translateY(-2px); }
    button:active, a:active { transform: translateY(2px) scale(0.97); }
    .launcher-wrap {
      width: min(100vw - 28px, 420px);
      min-height: 100dvh;
      display: grid;
      place-items: center;
      padding: 20px 0;
    }
    .launcher-panel {
      width: 100%;
      min-height: 560px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--panel);
      box-shadow: 0 24px 70px rgba(0, 0, 0, 0.78);
    }
    .titlebar {
      height: 50px;
      flex: 0 0 50px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 15px;
      user-select: none;
    }
    .brand {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 9px;
      color: var(--dim);
    }
    .brand-icon {
      width: 17px;
      height: 17px;
      border: 1px solid #444;
      border-radius: 5px;
      display: grid;
      place-items: center;
      color: #777;
      font-size: 10px;
      font-weight: 900;
    }
    .brand span {
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .window-actions { display: flex; align-items: center; gap: 8px; }
    .window-btn {
      min-height: 28px;
      width: 28px;
      padding: 0;
      background: transparent;
      color: #666;
      box-shadow: none;
      font-size: 18px;
      line-height: 1;
    }
    .window-btn:hover { color: #d1d5db; background: #1a1a1a; transform: none; }
    .status-center {
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 20px 28px 12px;
      text-align: center;
    }
    .status-orb {
      width: 104px;
      height: 104px;
      display: grid;
      place-items: center;
      margin-bottom: 24px;
      border-radius: 999px;
      background: #1a1a1a;
      border: 1px solid #222;
      transition: background 0.35s ease, box-shadow 0.35s ease, border-color 0.35s ease;
    }
    .status-light {
      width: 16px;
      height: 16px;
      border-radius: 999px;
      background: #5f6368;
      transition: background 0.35s ease, box-shadow 0.35s ease, transform 0.35s ease;
    }
    .launcher-panel.running .status-orb {
      background: #14241d;
      border-color: rgba(16, 185, 129, 0.28);
      box-shadow: 0 0 38px rgba(16, 185, 129, 0.18);
    }
    .launcher-panel.running .status-light {
      background: var(--green);
      box-shadow: 0 0 18px var(--green);
      transform: scale(1.08);
    }
    .launcher-panel.partial .status-orb {
      background: #272111;
      border-color: rgba(245, 158, 11, 0.28);
      box-shadow: 0 0 34px rgba(245, 158, 11, 0.14);
    }
    .launcher-panel.partial .status-light {
      background: #f59e0b;
      box-shadow: 0 0 16px #f59e0b;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 21px;
      line-height: 1.2;
      font-weight: 800;
      color: #d1d5db;
    }
    .launcher-panel.running h1 { color: #f9fafb; }
    .meta-pill {
      min-width: 0;
      max-width: 100%;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-soft);
      color: var(--dim);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      line-height: 1.3;
      white-space: nowrap;
    }
    .meta-pill span { overflow: hidden; text-overflow: ellipsis; }
    .dot-sep { color: #333; }
    .control-area {
      display: grid;
      gap: 13px;
      padding: 0 28px 18px;
    }
    .primary-btn {
      width: 100%;
      height: 56px;
      border: 1px solid var(--line-strong);
      background: linear-gradient(180deg, #2a2a2a, #1e1e1e);
      color: #e5e7eb;
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.46);
    }
    .primary-btn:hover { border-color: #4b5563; box-shadow: 0 16px 34px rgba(0, 0, 0, 0.58); }
    .launcher-panel.running .primary-btn {
      border-color: #4a2525;
      background: #2a1515;
      color: var(--red);
      box-shadow: 0 12px 30px rgba(127, 29, 29, 0.22);
    }
    .primary-btn.is-loading {
      pointer-events: none;
      opacity: 0.86;
      transform: translateY(1px) scale(0.985);
    }
    .primary-btn.is-loading::after {
      content: "";
      width: 15px;
      height: 15px;
      border: 2px solid rgba(255, 255, 255, 0.32);
      border-top-color: currentColor;
      border-radius: 999px;
      animation: spin 0.8s linear infinite;
    }
    .icon {
      width: 18px;
      height: 18px;
      display: inline-block;
      position: relative;
      flex: 0 0 18px;
    }
    .icon.play::before {
      content: "";
      position: absolute;
      inset: 3px 2px 3px 5px;
      background: currentColor;
      clip-path: polygon(0 0, 100% 50%, 0 100%);
    }
    .icon.stop::before {
      content: "";
      position: absolute;
      inset: 4px;
      border-radius: 2px;
      background: currentColor;
    }
    .secondary-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .ghost-btn, .ghost-link {
      height: 42px;
      border: 1px solid var(--line);
      background: transparent;
      color: #a3a3a3;
      box-shadow: none;
      font-size: 12px;
    }
    .ghost-btn:hover, .ghost-link:hover { background: var(--panel-soft); color: #e5e7eb; border-color: #3a3a3a; }
    .service-list {
      display: grid;
      gap: 8px;
      padding: 0 28px 18px;
    }
    .service-row {
      min-width: 0;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 10px 11px;
      border: 1px solid #1f1f1f;
      border-radius: 8px;
      background: #101010;
    }
    .service-name { color: #d4d4d4; font-size: 12px; font-weight: 800; }
    .service-meta { margin-top: 4px; color: #5f6368; font-size: 10px; line-height: 1.35; overflow-wrap: anywhere; }
    .service-state {
      min-width: 58px;
      padding: 5px 8px;
      border-radius: 999px;
      background: #1f1f1f;
      color: #737373;
      font-size: 11px;
      font-weight: 900;
      text-align: center;
    }
    .service-state.good { background: rgba(16, 185, 129, 0.12); color: var(--green); }
    .service-state.bad { background: rgba(248, 113, 113, 0.1); color: var(--red); }
    .footer {
      height: 40px;
      flex: 0 0 40px;
      border-top: 1px solid #1a1a1a;
      background: var(--panel-strong);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #555;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 10px;
      letter-spacing: 0.08em;
    }
    .log-drawer {
      display: none;
      margin: 0 28px 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #0a0a0a;
    }
    .log-drawer.open { display: block; }
    .log-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 9px 11px;
      border-bottom: 1px solid #1f1f1f;
      color: #a3a3a3;
      font-size: 11px;
      font-weight: 800;
    }
    pre {
      margin: 0;
      max-height: 170px;
      overflow: auto;
      padding: 10px 11px;
      color: #a7f3d0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 10px;
      line-height: 1.55;
    }
    .flash { animation: pulse-click 0.44s ease; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes pulse-click {
      0% { box-shadow: 0 0 0 0 rgba(96, 165, 250, 0.5), 0 12px 28px rgba(0, 0, 0, 0.46); }
      100% { box-shadow: 0 0 0 14px rgba(96, 165, 250, 0), 0 12px 28px rgba(0, 0, 0, 0.46); }
    }
    @media (max-width: 460px) {
      .launcher-wrap { width: min(100vw - 16px, 420px); padding: 8px 0; }
      .launcher-panel { min-height: calc(100dvh - 16px); }
      .status-center { padding-inline: 20px; }
      .control-area, .service-list { padding-inline: 20px; }
      .log-drawer { margin-inline: 20px; }
    }
  </style>
</head>
<body>
  <div class="launcher-wrap">
    <main id="panel" class="launcher-panel">
      <div class="titlebar">
        <div class="brand">
          <div class="brand-icon">AI</div>
          <span>Local Support Engine</span>
        </div>
        <div class="window-actions">
          <button class="window-btn" type="button" aria-label="最小化">-</button>
          <button class="window-btn" type="button" aria-label="关闭">×</button>
        </div>
      </div>

      <section class="status-center">
        <div class="status-orb"><div class="status-light"></div></div>
        <h1 id="mainTitle">正在检测服务</h1>
        <div class="meta-pill">
          <span id="mainAddress">Localhost: 8000</span>
          <span class="dot-sep">|</span>
          <span id="mainMeta">Qdrant: -</span>
        </div>
      </section>

      <section class="control-area">
        <button id="primaryControl" class="primary-btn" type="button" onclick="primaryAction(this)">
          <span id="primaryIcon" class="icon play"></span>
          <span id="primaryText">启动客服引擎</span>
        </button>
        <div class="secondary-row">
          <button class="ghost-btn" type="button" onclick="toggleLogs()">日志查看</button>
          <a class="ghost-link" href="http://127.0.0.1:8000/admin/settings">配置参数</a>
        </div>
      </section>

      <section class="service-list">
        <div class="service-row">
          <div>
            <div class="service-name">FastAPI 业务服务</div>
            <div id="appMeta" class="service-meta">-</div>
          </div>
          <div id="appState" class="service-state">-</div>
        </div>
        <div class="service-row">
          <div>
            <div class="service-name">Qdrant 向量库</div>
            <div id="qdrantMeta" class="service-meta">-</div>
          </div>
          <div id="qdrantState" class="service-state">-</div>
        </div>
      </section>

      <section id="logDrawer" class="log-drawer">
        <div class="log-head">
          <span>运行反馈</span>
          <button class="window-btn" type="button" onclick="toggleLogs()" aria-label="关闭日志">×</button>
        </div>
        <pre id="message">加载中...</pre>
      </section>

      <div class="footer">
        <span id="footerText">CPU: - / RAM: -</span>
      </div>
    </main>
  </div>
  <script>
    let latestStatus = null;

    function setService(elId, running) {
      const el = document.querySelector(elId);
      if (!el) return;
      el.textContent = running ? '运行中' : '未运行';
      el.className = 'service-state ' + (running ? 'good' : 'bad');
    }

    function updatePrimary(appRunning, qdrantRunning) {
      const panel = document.querySelector('#panel');
      const title = document.querySelector('#mainTitle');
      const primaryIcon = document.querySelector('#primaryIcon');
      const primaryText = document.querySelector('#primaryText');
      const allRunning = appRunning && qdrantRunning;
      panel.classList.toggle('running', allRunning);
      panel.classList.toggle('partial', !allRunning && (appRunning || qdrantRunning));
      title.textContent = allRunning ? '服务运行中' : appRunning || qdrantRunning ? '部分服务运行中' : '服务未启动';
      primaryIcon.className = 'icon ' + (allRunning ? 'stop' : 'play');
      primaryText.textContent = allRunning ? '停止运行引擎' : '启动客服引擎';
    }

    async function status() {
      const data = await fetch('/api/system/status').then(r => r.json());
      latestStatus = data;
      const app = data.app || data;
      const qdrant = data.qdrant || {};
      const appRunning = !!app.running;
      const qdrantRunning = !!qdrant.running;
      updatePrimary(appRunning, qdrantRunning);
      setService('#appState', appRunning);
      setService('#qdrantState', qdrantRunning);
      document.querySelector('#mainAddress').textContent = app.url ? `Localhost: ${app.port || 8000}` : 'Localhost: 8000';
      document.querySelector('#mainMeta').textContent = `Qdrant: ${qdrantRunning ? 'online' : 'offline'}`;
      document.querySelector('#appMeta').textContent = appRunning ? `PID ${app.pid || '-'} ｜ ${app.url || '-'}` : '聊天页和后台未启动';
      document.querySelector('#qdrantMeta').textContent = qdrantRunning ? `${qdrant.mode || '-'} ｜ ${qdrant.url || '-'}` : (qdrant.availability_message || '知识库未启动');
      document.querySelector('#footerText').textContent = `APP: ${appRunning ? 'ON' : 'OFF'} / VECTOR: ${qdrantRunning ? 'ON' : 'OFF'}`;
      document.querySelector('#message').textContent = JSON.stringify(data, null, 2);
    }

    function toggleLogs() {
      document.querySelector('#logDrawer').classList.toggle('open');
    }

    async function primaryAction(button) {
      const data = latestStatus || {};
      const app = data.app || data;
      const qdrant = data.qdrant || {};
      const allRunning = !!app.running && !!qdrant.running;
      await act(allRunning ? 'stop-all' : 'start-all', button);
    }

    async function act(name, button) {
      const originalText = button ? button.textContent : '';
      if (button) {
        button.classList.remove('flash');
        void button.offsetWidth;
        button.classList.add('flash', 'is-loading');
        if (button.id === 'primaryControl') {
          document.querySelector('#primaryText').textContent = '处理中';
        } else {
          button.textContent = '处理中';
        }
      }
      try {
        const data = await fetch('/api/system/' + name, { method: 'POST' }).then(r => r.json());
        document.querySelector('#message').textContent = JSON.stringify(data, null, 2);
        setTimeout(status, 800);
      } catch (err) {
        document.querySelector('#message').textContent = '操作失败：' + err;
      } finally {
        if (button) {
          setTimeout(() => {
            button.classList.remove('is-loading');
            if (button.id !== 'primaryControl') button.textContent = originalText;
            status();
          }, 420);
        }
      }
    }

    status();
    setInterval(status, 5000);
  </script>
</body>
</html>""".replace("__BASE_DIR__", str(BASE_DIR))

def main():
    server = ReusableThreadingHTTPServer(("127.0.0.1", 7999), LauncherHandler)
    print("Launcher running at http://127.0.0.1:7999")
    server.serve_forever()


if __name__ == "__main__":
    main()
