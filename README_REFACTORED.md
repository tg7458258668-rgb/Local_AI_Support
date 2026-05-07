# Local AI Support Refactor

这是一份独立重构副本，原始项目目录 `/Users/ai_studio/ai-cs-mvp` 未被修改。

## 目标

- 保留现有本地 RAG 能力：FAQ、文档知识库、优先规则、Ollama、Qdrant。
- 新增 API-first 架构，方便后续接入微信、飞书、网页客服、CRM 等渠道。
- 将代码拆成清晰边界：HTTP API、业务服务、数据仓库、渠道适配器。

## 新架构

```text
support_app/
  main.py                  # 新 FastAPI 入口
  settings.py              # 环境配置
  schemas.py               # 统一请求/响应模型
  dependencies.py          # 依赖组装
  api/v1/                  # HTTP 路由，只做参数接收和响应返回
  services/                # 聊天编排、Ollama、提示词
  repositories/            # Qdrant、规则 CSV、FAQ JSON、分类 JSON、文档切块
  adapters/                # 微信/飞书等渠道适配
```

旧目录 `app/` 和 `scripts/` 保留为 legacy 参考。新的二次开发优先从 `support_app/` 开始。

## 分层约定

- `api/v1/`: 不写业务逻辑，不直接读写文件，不直接调用 Qdrant/Ollama。
- `services/`: 放业务编排。例如聊天路由判断、FAQ 重新入库、后台管理流程。
- `repositories/`: 放数据访问。例如 JSON/CSV 文件、Qdrant 检索。
- `adapters/`: 放外部渠道差异。例如微信、飞书、网页客服、企业微信。
- `schemas.py`: 放跨层传输模型。新增接口时先定义请求/响应模型。

这样后续接微信、飞书、企微或 CRM 时，只新增 adapter 和少量 router，不需要改核心 RAG。

## 运行

```bash
cd /Users/ai_studio/ai-cs-mvp-refactor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn support_app.main:app --reload --port 8000
```

需要本机已有：

- Qdrant: `http://localhost:6333`
- Ollama: `http://localhost:11434`
- Ollama 模型：`bge-m3`、`qwen3:8b`

## 统一聊天接口

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

响应会包含：

- `answer`: 客服回答
- `route`: `faq` / `doc` / `handoff` / `fallback` / `error`
- `need_human`: 是否建议人工确认
- `sources`: 命中的 FAQ 或文档来源
- `timings`: 规则匹配、检索、生成等耗时

## 微信/飞书接入方式

统一入口：

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

新增渠道时，只需要：

1. 在 `support_app/adapters/` 新建适配器，实现 `parse()` 和 `render()`。
2. 在 `support_app/api/v1/integrations.py` 的 `ADAPTERS` 注册。
3. 不需要改 `ChatService`。

## 兼容旧接口

为了降低迁移成本，保留旧式入口：

```text
POST /ask
{"question": "电池保修多久？"}
```

建议新代码使用 `/api/v1/chat`。

## 后台管理接口

新版后台 API 已从旧 `app/main.py` 拆出：

```text
GET    /api/v1/admin/summary
GET    /api/v1/admin/docs
GET    /api/v1/admin/faqs
POST   /api/v1/admin/faqs
PUT    /api/v1/admin/faqs/{faq_id}
DELETE /api/v1/admin/faqs/{faq_id}
POST   /api/v1/admin/faqs/reindex
GET    /api/v1/admin/rules
POST   /api/v1/admin/rules
PUT    /api/v1/admin/rules/{rule_id}
DELETE /api/v1/admin/rules/{rule_id}
POST   /api/v1/admin/rules/test
GET    /api/v1/admin/categories
POST   /api/v1/admin/categories
DELETE /api/v1/admin/categories/{category_name}
```

后台路由只负责 HTTP，具体逻辑在 `AdminService`，文件读写在 repository。

## 二次开发建议

- 新增聊天渠道：加 `support_app/adapters/<channel>.py`，然后注册到 `integrations.py`。
- 新增知识来源：加 repository，再由 service 编排，不要直接在 router 读文件。
- 新增模型供应商：实现新的 LLM client，替换 `OllamaClient` 注入即可。
- 调整问答路由策略：优先改 `ChatService._route()`，不要散落在 API 层。
- 调整提示词：只改 `services/prompt_builder.py`。
