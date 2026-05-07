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
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f6f7f9; color: #111827; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(720px, calc(100vw - 32px)); background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; box-shadow: 0 18px 50px rgba(15, 23, 42, .08); }
    h1 { margin: 0 0 8px; font-size: 24px; letter-spacing: 0; }
    p { color: #6b7280; line-height: 1.7; }
    .status { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
    .item { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }
    .service { display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: center; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; }
    .label { color: #6b7280; font-size: 13px; }
    .value { margin-top: 6px; font-weight: 700; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
    button, a { border: 0; border-radius: 8px; padding: 11px 16px; background: #2563eb; color: #fff; text-decoration: none; font-size: 14px; cursor: pointer; }
    button.secondary { background: #111827; }
    button.danger { background: #dc2626; }
    .small-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .small-actions button { padding: 8px 11px; font-size: 13px; }
    .muted { color: #6b7280; font-size: 13px; margin-top: 6px; }
    .path { margin: 12px 0 0; padding: 10px 12px; border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc; color: #334155; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }
    pre { background: #f3f4f6; border-radius: 8px; padding: 12px; white-space: pre-wrap; overflow-wrap: anywhere; height: min(34vh, 280px); max-height: 280px; overflow: auto; }
    @media (max-width: 680px) { .status { grid-template-columns: 1fr; } .service { grid-template-columns: 1fr; } .small-actions { justify-content: flex-start; } }
  </style>
</head>
<body>
  <main>
    <h1>本地 AI 客服启动器</h1>
    <p>这个页面独立运行在 7999 端口。即使客服系统 8000 端口没有启动，也可以在这里启动、停止或重启业务服务和 Qdrant 向量库。</p>
    <div class="path">当前启动目录：__BASE_DIR__</div>
    <section class="status">
      <div class="service">
        <div>
          <div class="label">业务服务 FastAPI</div>
          <div id="appRunning" class="value">-</div>
          <div id="appMeta" class="muted">-</div>
        </div>
        <div class="small-actions">
          <button onclick="act('app/start')">启动</button>
          <button class="secondary" onclick="act('app/restart')">重启</button>
          <button class="danger" onclick="act('app/stop')">关闭</button>
        </div>
      </div>
      <div class="service">
        <div>
          <div class="label">Qdrant 向量库</div>
          <div id="qdrantRunning" class="value">-</div>
          <div id="qdrantMeta" class="muted">-</div>
        </div>
        <div class="small-actions">
          <button onclick="act('qdrant/start')">启动</button>
          <button class="secondary" onclick="act('qdrant/restart')">重启</button>
          <button class="danger" onclick="act('qdrant/stop')">关闭</button>
        </div>
      </div>
    </section>
    <div class="actions">
      <button onclick="act('start-all')">启动全部</button>
      <button class="secondary" onclick="act('restart-all')">重启全部</button>
      <button class="danger" onclick="act('stop-all')">关闭全部</button>
      <a href="http://127.0.0.1:8000/admin">进入管理后台</a>
      <a href="http://127.0.0.1:8000/">进入聊天页</a>
    </div>
    <pre id="message">加载中...</pre>
  </main>
  <script>
    async function status() {
      const data = await fetch('/api/system/status').then(r => r.json());
      const app = data.app || data;
      const qdrant = data.qdrant || {};
      document.querySelector('#appRunning').textContent = app.running ? '运行中' : '未运行';
      document.querySelector('#appMeta').textContent = `PID：${app.pid || '-'} ｜ 地址：${app.url || '-'} ｜ 目录：${app.base_dir || data.base_dir || '-'}`;
      document.querySelector('#qdrantRunning').textContent = qdrant.running ? '运行中' : '未运行';
      const dockerState = qdrant.docker_ready ? 'Docker 已就绪' : (qdrant.docker_error || 'Docker 未就绪');
      document.querySelector('#qdrantMeta').textContent = `方式：${qdrant.mode || '-'} ｜ ${qdrant.availability_message || qdrant.url || '-'} ｜ Docker：${qdrant.docker_path || '-'} ｜ ${dockerState} ｜ 存储：${qdrant.storage_dir || '-'}`;
      document.querySelector('#message').textContent = JSON.stringify(data, null, 2);
    }
    async function act(name) {
      const data = await fetch('/api/system/' + name, { method: 'POST' }).then(r => r.json());
      document.querySelector('#message').textContent = JSON.stringify(data, null, 2);
      setTimeout(status, 800);
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
