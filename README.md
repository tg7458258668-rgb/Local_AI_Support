# Local AI Support

本项目是一个本地运行的 AI 客服与销售支持系统，面向 U-MOCO 产品资料、FAQ、报价规则、售后政策和多渠道客服接入场景。系统以 FastAPI 为核心，保留本地 RAG、Ollama 和 Qdrant 能力，并把聊天、后台管理、知识库维护、渠道适配拆成清晰模块，方便继续迭代。

## 版本状态

| 项目 | 当前值 |
| --- | --- |
| 当前版本 | `v2.3.1` |
| GitHub 仓库 | `tg7458258668-rgb/Local_AI_Support` |
| 主应用入口 | `support_app.main:app` |
| 发布流程 | `docs/RELEASE_WORKFLOW.md` |
| 版本记录 | `CHANGELOG.md` |

## 快速入口

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn support_app.main:app --reload --port 8000
```

- 聊天页：`http://localhost:8000/chat`
- 管理后台：`http://localhost:8000/admin`
- API 文档：`http://localhost:8000/docs`

## 后续上传到 GitHub

每次发布按 `docs/RELEASE_WORKFLOW.md` 执行，核心顺序是：

1. 更新 `VERSION`、`support_app/main.py`、README 顶部版本和 `CHANGELOG.md`。
2. 清理本地缓存、日志、pid、临时文件和文档页面预览缓存。
3. 运行 Python 编译、pytest 和 JS 语法检查。
4. 提交为 `Release vX.Y.Z`，创建同名 tag，并推送 `main` 和 tag。

本仓库还内置了 `.agents/skills/github-repo-release`，后续可直接让 Codex 使用 `$github-repo-release` 执行同一套流程。

## 功能概览

- 本地 AI 客服问答：支持 FAQ、文档知识库、报价、售后和兜底转人工。
- API-first 架构：统一聊天接口可接入网页、微信、飞书、企微或 CRM。
- 管理后台：维护 FAQ、分类、优先规则、文档、报价目录、行为规则和回归测试。
- 本地知识库：支持 PDF/文档解析、切块、检索、OCR 页面预览缓存。
- 多轮上下文：保留客户记忆、会话历史、报价草稿和反馈数据。
- 本地启动器：提供 macOS 启动脚本，便于非命令行方式运行服务。

## 项目结构

```text
support_app/              # 新版 FastAPI 应用
  api/v1/                 # HTTP API 路由
  adapters/               # 微信、飞书等渠道适配器
  repositories/           # JSON、CSV、Qdrant 等数据访问
  services/               # 聊天编排、检索、报价、后台管理等业务逻辑
  main.py                 # 新版应用入口

app/                      # 旧版页面与兼容模块
data/                     # FAQ、规则、报价、文档切块等本地数据
scripts/                  # 知识库构建、文档解析、调试脚本
tests/                    # 单元测试与回归测试
tools/                    # 文档处理、启动器辅助工具
support_launcher.py       # 本地服务启动器
本地AI客服启动器.command    # macOS 双击启动入口
```

旧目录 `app/` 仍用于静态页面和兼容逻辑；新功能优先放在 `support_app/`。

## 环境要求

- Python 3.11+
- Qdrant：默认 `http://localhost:6333`
- Ollama：默认 `http://localhost:11434`
- Ollama 模型：`bge-m3`、`qwen3:8b`

## 本地启动

```bash
cd /Users/ai_studio/ai-cs-mvp-refactor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn support_app.main:app --reload --port 8000
```

启动后访问：

- 聊天页：`http://localhost:8000/chat`
- 管理后台：`http://localhost:8000/admin`
- API 文档：`http://localhost:8000/docs`

macOS 也可以双击 `本地AI客服启动器.command` 启动本地服务。

## 核心接口

### 健康检查

```bash
curl http://localhost:8000/api/v1/health
```

### 统一聊天接口

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "电池保修多久？",
    "channel": "api",
    "conversation_id": "demo-001",
    "user_id": "user-001"
  }'
```

响应字段包括：

- `answer`：客服回答
- `route`：`faq`、`doc`、`quote`、`handoff`、`fallback` 或 `error`
- `need_human`：是否建议人工确认
- `sources`：命中的 FAQ 或文档来源
- `timings`：规则匹配、检索、生成等耗时

### 兼容旧接口

```text
POST /ask
{"question": "电池保修多久？"}
```

建议新接入统一使用 `/api/v1/chat`。

## 多渠道接入

统一 webhook：

```text
POST /api/v1/integrations/webhook
```

微信示例：

```json
{
  "channel": "wechat",
  "payload": {
    "Content": "主机保修多久？",
    "FromUserName": "wechat-user",
    "MsgId": "msg-001"
  }
}
```

飞书示例：

```json
{
  "channel": "feishu",
  "payload": {
    "event": {
      "message": {
        "content": "电池保修多久？",
        "chat_id": "chat-001"
      },
      "sender": {
        "sender_id": {
          "open_id": "feishu-user"
        }
      }
    }
  }
}
```

新增渠道时，在 `support_app/adapters/` 新建适配器，实现 `parse()` 和 `render()`，再到 `support_app/api/v1/integrations.py` 注册即可。

## 数据与安全

仓库会保留业务规则、FAQ、报价、文档解析结果等可复用数据。以下内容不会上传到 GitHub：

- `.venv/`、`__pycache__/`、测试缓存
- `.env`、本地密钥和环境变量
- `runtime/` 运行日志与 pid 文件
- `data/qdrant_storage/` 本地向量库存储
- `data/doc_page_images/` 按需生成的文档页面预览缓存
- `tmp_docx_inspect/` 临时文档检查输出

如需提供环境变量模板，请更新 `.env.example`，不要提交真实密钥。

## 测试与检查

```bash
python3 -m compileall support_app app scripts
python3 -m pytest
node --check app/static/admin.js
node --check app/static/chat-v2.js
```

如果本地没有安装 Node.js，可以先跳过 JS 语法检查；Python 编译和 pytest 是发布前的主要检查。

## 二次开发建议

- 新增 API：先在 `support_app/schemas.py` 定义请求/响应模型，再增加 router 和 service。
- 新增知识来源：新增 repository，由 service 编排，不要在 router 里直接读写文件。
- 调整路由策略：优先修改 `support_app/services/chat_service.py`。
- 调整提示词：集中修改 `support_app/services/prompt_builder.py`。
- 替换模型供应商：实现新的 LLM client，再通过依赖注入替换现有 Ollama client。
