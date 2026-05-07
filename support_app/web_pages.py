from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def html_head_response() -> Response:
    return Response(status_code=200, media_type="text/html; charset=utf-8")


@router.get("/")
def chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="chat.html", context={})


@router.head("/")
def chat_page_head():
    return html_head_response()


@router.get("/admin")
def legacy_admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html", context={})


@router.head("/admin")
def legacy_admin_page_head():
    return html_head_response()


@router.head("/admin-ui")
def admin_page_head():
    return html_head_response()


@router.get("/admin-ui", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse("""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>本地 AI 客服管理概览</title>
  <style>
    body { margin: 0; background: #f6f7f9; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { height: 64px; display: flex; align-items: center; justify-content: space-between; padding: 0 28px; background: #fff; border-bottom: 1px solid #e5e7eb; }
    h1 { font-size: 20px; margin: 0; letter-spacing: 0; }
    a { color: #2563eb; text-decoration: none; font-size: 14px; }
    main { max-width: 1100px; margin: 0 auto; padding: 24px; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
    .stat, .panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }
    .label { color: #6b7280; font-size: 13px; }
    .value { font-size: 28px; font-weight: 700; margin-top: 8px; }
    .panel { margin-top: 14px; }
    .tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .tag { background: #eef2ff; color: #3730a3; border-radius: 999px; padding: 5px 10px; font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; background: #fff; }
    th, td { border-bottom: 1px solid #e5e7eb; text-align: left; padding: 10px; font-size: 14px; vertical-align: top; }
    th { color: #6b7280; font-weight: 600; }
    @media (max-width: 760px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  </style>
</head>
<body>
  <header>
    <h1>管理概览</h1>
    <a href="/">返回聊天页</a>
  </header>
  <main>
    <section class="grid">
      <div class="stat"><div class="label">文档数</div><div id="doc_count" class="value">-</div></div>
      <div class="stat"><div class="label">文档片段</div><div id="doc_chunk_count" class="value">-</div></div>
      <div class="stat"><div class="label">FAQ</div><div id="faq_count" class="value">-</div></div>
      <div class="stat"><div class="label">规则</div><div id="rule_count" class="value">-</div></div>
    </section>
    <section class="panel">
      <h2>文档名称</h2>
      <div id="docs" class="tags"></div>
    </section>
    <section class="panel">
      <h2>分类</h2>
      <table>
        <thead><tr><th>分类</th><th>FAQ 使用</th><th>规则使用</th></tr></thead>
        <tbody id="categories"></tbody>
      </table>
    </section>
  </main>
  <script>
    async function load() {
      const summary = await fetch("/api/v1/admin/summary").then(r => r.json());
      for (const key of ["doc_count", "doc_chunk_count", "faq_count", "rule_count"]) {
        document.querySelector("#" + key).textContent = summary[key] ?? 0;
      }
      document.querySelector("#docs").innerHTML = (summary.doc_names || []).map(name => `<span class="tag">${name}</span>`).join("") || "<span class='tag'>暂无文档</span>";
      const categories = await fetch("/api/v1/admin/categories").then(r => r.json());
      document.querySelector("#categories").innerHTML = (categories.items || []).map(item => `
        <tr><td>${item.name}</td><td>${item.faq_count}</td><td>${item.rule_count}</td></tr>
      `).join("");
    }
    load().catch(err => alert("加载失败：" + err));
  </script>
</body>
</html>
""")
